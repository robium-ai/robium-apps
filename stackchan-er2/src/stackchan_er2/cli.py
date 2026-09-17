"""Repository-local command line surface."""

from __future__ import annotations

import argparse
import asyncio
import os
import platform
import shutil
import statistics
import sys
from pathlib import Path
from typing import Any

from .agent import StackChanAgent, function_declarations
from .audio import FakeTTS, MacSayTTS
from .config import ANIMATION_NAMES, LEGO_DIRECTIONS, LEGO_SCAN_TIMEOUT, MODEL, SAMPLE_RATE
from .device import DeviceError, FakeStackChan, GuardedActions, SerialStackChan, discover_port
from .lego import FakeLegoRobot, LegoDriveSession, LegoError, scan_hubs
from .lego import hardware_smoke as lego_hardware_smoke


def _add_lego_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--lego-hub-name", help="exact Pybricks Bluetooth hub name")
    parser.add_argument(
        "--lego-scan-timeout",
        type=float,
        default=LEGO_SCAN_TIMEOUT,
        help="seconds to scan for the LEGO hub",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gemini Robotics ER 2 for STACK-CHAN")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor")
    commands.add_parser("tools")
    commands.add_parser("demo")

    device_doctor = commands.add_parser("device-doctor")
    device_doctor.add_argument("--port")

    hardware_smoke = commands.add_parser("hardware-smoke")
    hardware_smoke.add_argument("--port")

    camera = commands.add_parser("camera")
    camera.add_argument("--port")
    camera.add_argument("--output", type=Path, default=Path("stackchan-view.jpg"))

    animate = commands.add_parser("animate")
    animate.add_argument("animation", choices=ANIMATION_NAMES)
    animate.add_argument("--port")

    lego_doctor = commands.add_parser("lego-doctor")
    _add_lego_options(lego_doctor)

    lego_smoke = commands.add_parser("lego-smoke")
    _add_lego_options(lego_smoke)

    lego_drive = commands.add_parser("lego-drive")
    lego_drive.add_argument("direction", choices=LEGO_DIRECTIONS)
    _add_lego_options(lego_drive)

    run = commands.add_parser("run")
    run.add_argument("--port")
    run.add_argument("--listen-seconds", type=float, default=4.0)
    run.add_argument(
        "--push-to-talk",
        action="store_true",
        help="press Enter for each fixed-length recording instead of listening continuously",
    )
    run.add_argument("--text", help="send one text turn instead of recording voice")
    run.add_argument("--voice", help="optional macOS say voice")
    run.add_argument(
        "--no-lego",
        action="store_true",
        help="run Stack Chan without connecting the LEGO robot",
    )
    _add_lego_options(run)
    return parser


def doctor() -> int:
    checks: list[tuple[str, bool, str]] = []
    checks.append(("platform", platform.system() == "Darwin", platform.platform()))
    checks.append(("say", shutil.which("say") is not None, shutil.which("say") or "missing"))
    checks.append(
        ("afconvert", shutil.which("afconvert") is not None, shutil.which("afconvert") or "missing")
    )
    try:
        port = discover_port()
        checks.append(("stackchan", True, port))
    except DeviceError as error:
        checks.append(("stackchan", False, str(error)))
    key_present = bool(os.environ.get("GEMINI_API_KEY"))
    checks.append(("gemini-key", key_present, "set" if key_present else "unset (needed for run)"))
    checks.append(("model", True, MODEL))
    try:
        import bleak  # noqa: F401

        checks.append(("lego-bluetooth", True, "bleak installed"))
    except ImportError:
        checks.append(("lego-bluetooth", False, "bleak missing; run ./app build"))
    for name, passed, detail in checks:
        label = "PASS" if passed else ("WARN" if name == "gemini-key" else "FAIL")
        print(f"{label} {name}: {detail}")
    return 1 if any(not passed and name != "gemini-key" for name, passed, _ in checks) else 0


def device_doctor(port: str | None) -> int:
    with SerialStackChan(port) as device:
        state = device.status()
    print(f"PASS STACK-CHAN firmware on {discover_port(port)}: {state}")
    return 0


def capture_camera(port: str | None, output: Path) -> int:
    with SerialStackChan(port) as device:
        image = device.capture_image()
    output.write_bytes(image)
    print(f"PASS saved {len(image)}-byte STACK-CHAN image to {output}")
    return 0


def animate(port: str | None, animation: str) -> int:
    with SerialStackChan(port) as device:
        result = device.animate(animation)
    print(f"PASS STACK-CHAN animation {animation}: {result}")
    return 0


def demo() -> int:
    device = FakeStackChan()
    lego = FakeLegoRobot()
    actions = GuardedActions(device, FakeTTS(), lego)
    actions.execute("move_head", {"yaw": 20, "pitch": 50, "speed": 150})
    actions.execute("show_text", {"text": "Hello!"})
    actions.execute("speak", {"message": "Hello from STACK-CHAN."})
    actions.execute("look", {})
    actions.execute("animate", {"animation": "nod_yes"})
    actions.execute("drive_lego", {"direction": "forward"})
    assert [name for name, _ in device.events] == [
        "move_head",
        "show_text",
        "show_text",
        "speak_pcm",
        "capture_image",
        "animate",
    ]
    assert lego.events[-1]["direction"] == "forward"
    for name, payload in device.events:
        print(f"[fake] {name}: {payload}")
    print("STACKCHAN ER2 MOCK PASS")
    return 0


async def lego_doctor(hub_name: str | None, scan_timeout: float) -> int:
    hubs = await scan_hubs(scan_timeout)
    if not hubs:
        raise LegoError("No advertising Pybricks hub found")
    for hub in hubs:
        print(f"PASS found LEGO hub: {hub.name} ({hub.address})")
    if hub_name and not any(hub.name.casefold() == hub_name.casefold() for hub in hubs):
        raise LegoError(f"No advertising LEGO hub named {hub_name!r} found")
    return 0


async def lego_smoke(hub_name: str | None, scan_timeout: float) -> int:
    print("Keeping LEGO motor power at zero for the hardware smoke check.")
    hub = await lego_hardware_smoke(hub_name, scan_timeout)
    print(f"PASS LEGO bridge READY and PING/PONG: {hub.name} ({hub.address})")
    return 0


def lego_drive(hub_name: str | None, scan_timeout: float, direction: str) -> int:
    lego = LegoDriveSession(hub_name=hub_name, scan_timeout=scan_timeout)
    try:
        state = lego.start()
        print(f"Connected to {state.hub_name}; running bounded {direction} command.")
        result = lego.drive(direction)
        print(f"PASS LEGO {direction}: {result}")
    finally:
        lego.close()
    return 0


def _pcm_peak_mean(pcm: bytes) -> tuple[int, float]:
    samples = [int.from_bytes(pcm[i : i + 2], "little", signed=True) for i in range(0, len(pcm), 2)]
    absolute = [abs(sample) for sample in samples]
    return max(absolute, default=0), statistics.fmean(absolute) if absolute else 0.0


def hardware_smoke(port: str | None) -> int:
    tts = MacSayTTS()
    with SerialStackChan(port) as device:
        initial = device.status()
        yaw = int(initial.get("yaw", 0))
        pitch = int(initial.get("pitch", 45))
        probe_yaw = max(-10, min(10, yaw + (10 if yaw <= 0 else -10)))
        device.show_text("STACK-CHAN ER2\nHardware smoke")
        device.move_head(probe_yaw, max(5, min(85, pitch)), 150)
        device.move_head(yaw, max(5, min(85, pitch)), 150)
        print("Speak toward STACK-CHAN for the one-second microphone check...")
        pcm = device.record_audio(1.0)
        peak, mean = _pcm_peak_mean(pcm)
        if len(pcm) != SAMPLE_RATE * 2:
            raise DeviceError(f"microphone returned {len(pcm)} bytes, expected {SAMPLE_RATE * 2}")
        message = "STACK-CHAN hardware smoke passed."
        device.show_text(message)
        device.speak_pcm(tts.synthesize(message))
        final = device.status()
        image = device.capture_image()
    print(
        "PASS real STACK-CHAN: "
        f"motion restored to yaw={final.get('yaw')} pitch={final.get('pitch')}; "
        f"microphone peak={peak} mean={mean:.1f}; display and speaker completed"
        f"; camera returned {len(image)} JPEG bytes"
    )
    return 0


async def run_agent(arguments: Any) -> int:
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is unset; export it before ./app run")
    lego = None
    try:
        if not arguments.no_lego:
            lego = LegoDriveSession(
                hub_name=arguments.lego_hub_name,
                scan_timeout=arguments.lego_scan_timeout,
            )
            state = await asyncio.to_thread(lego.start)
            print(f"LEGO robot connected: {state.hub_name}")
        with SerialStackChan(arguments.port) as device:
            actions = GuardedActions(device, MacSayTTS(arguments.voice), lego)
            agent = StackChanAgent(key, device, actions, lego_enabled=lego is not None)
            await agent.run(
                listen_seconds=arguments.listen_seconds,
                text=arguments.text,
                push_to_talk=arguments.push_to_talk,
            )
    finally:
        if lego is not None:
            await asyncio.to_thread(lego.close)
    return 0


def main() -> None:
    arguments = _parser().parse_args()
    try:
        if arguments.command == "doctor":
            code = doctor()
        elif arguments.command == "device-doctor":
            code = device_doctor(arguments.port)
        elif arguments.command == "hardware-smoke":
            code = hardware_smoke(arguments.port)
        elif arguments.command == "camera":
            code = capture_camera(arguments.port, arguments.output)
        elif arguments.command == "animate":
            code = animate(arguments.port, arguments.animation)
        elif arguments.command == "lego-doctor":
            code = asyncio.run(
                lego_doctor(arguments.lego_hub_name, arguments.lego_scan_timeout)
            )
        elif arguments.command == "lego-smoke":
            code = asyncio.run(
                lego_smoke(arguments.lego_hub_name, arguments.lego_scan_timeout)
            )
        elif arguments.command == "lego-drive":
            code = lego_drive(
                arguments.lego_hub_name,
                arguments.lego_scan_timeout,
                arguments.direction,
            )
        elif arguments.command == "demo":
            code = demo()
        elif arguments.command == "tools":
            for declaration in function_declarations():
                print(declaration["name"])
            code = 0
        else:
            code = asyncio.run(run_agent(arguments))
    except (DeviceError, LegoError, RuntimeError, ValueError) as error:
        print(f"ERROR {error}", file=sys.stderr)
        code = 1
    except KeyboardInterrupt:
        print("\nStopped continuous listening.")
        code = 130
    raise SystemExit(code)
