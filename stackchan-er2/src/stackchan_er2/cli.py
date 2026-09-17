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
from .config import ANIMATION_NAMES, MODEL, SAMPLE_RATE
from .device import DeviceError, FakeStackChan, GuardedActions, SerialStackChan, discover_port


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
    actions = GuardedActions(device, FakeTTS())
    actions.execute("move_head", {"yaw": 20, "pitch": 50, "speed": 150})
    actions.execute("show_text", {"text": "Hello!"})
    actions.execute("speak", {"message": "Hello from STACK-CHAN."})
    actions.execute("look", {})
    actions.execute("animate", {"animation": "nod_yes"})
    assert [name for name, _ in device.events] == [
        "move_head",
        "show_text",
        "show_text",
        "speak_pcm",
        "capture_image",
        "animate",
    ]
    for name, payload in device.events:
        print(f"[fake] {name}: {payload}")
    print("STACKCHAN ER2 MOCK PASS")
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
    with SerialStackChan(arguments.port) as device:
        actions = GuardedActions(device, MacSayTTS(arguments.voice))
        agent = StackChanAgent(key, device, actions)
        await agent.run(
            listen_seconds=arguments.listen_seconds,
            text=arguments.text,
            push_to_talk=arguments.push_to_talk,
        )
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
        elif arguments.command == "demo":
            code = demo()
        elif arguments.command == "tools":
            for declaration in function_declarations():
                print(declaration["name"])
            code = 0
        else:
            code = asyncio.run(run_agent(arguments))
    except (DeviceError, RuntimeError, ValueError) as error:
        print(f"ERROR {error}", file=sys.stderr)
        code = 1
    except KeyboardInterrupt:
        print("\nStopped continuous listening.")
        code = 130
    raise SystemExit(code)
