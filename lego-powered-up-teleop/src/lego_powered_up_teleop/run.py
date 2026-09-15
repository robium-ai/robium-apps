"""Command-line entry point for setup, diagnostics, smoke, and UI."""

from __future__ import annotations

import argparse
import asyncio
import os
import time
from pathlib import Path

from .link import LinkError, choose_candidate, hardware_smoke, scan_hubs

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

APP_ROOT = Path(__file__).resolve().parents[2]
HUB_PROGRAM = APP_ROOT / "hub" / "main.py"


def _add_hub_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--hub-name", help="exact Bluetooth name; required if several hubs advertise")
    parser.add_argument("--scan-timeout", type=float, default=10.0, help="Bluetooth scan seconds")


async def _list_hubs(timeout: float) -> int:
    candidates = await scan_hubs(timeout)
    if not candidates:
        print("No advertising Pybricks hubs found.")
        return 1
    for candidate in candidates:
        print(f"{candidate.name}\t{candidate.address}")
    return 0


async def _doctor(hub_name: str | None, timeout: float) -> int:
    ok = True
    if HUB_PROGRAM.is_file():
        print(f"ok: hub bridge present at {HUB_PROGRAM}")
    else:
        print(f"FAIL: missing hub bridge at {HUB_PROGRAM}")
        ok = False
    try:
        import bleak
        import pygame

        bleak_version = bleak.__version__ if hasattr(bleak, "__version__") else "installed"
        print(f"ok: bleak {bleak_version}")
        print(f"ok: pygame {pygame.version.ver}")
    except ImportError as exc:
        print(f"FAIL: missing Python dependency: {exc}. Run './app build'.")
        return 1

    try:
        candidate = choose_candidate(await scan_hubs(timeout), hub_name)
        print(f"ok: found {candidate.name} ({candidate.address})")
    except LinkError as exc:
        print(f"FAIL: {exc}")
        ok = False
    print("DOCTOR PASS" if ok else "DOCTOR FAIL")
    return 0 if ok else 1


async def _smoke(hub_name: str | None, timeout: float) -> int:
    print("Keeping motor power at zero for the hardware smoke check.")
    try:
        candidate = await hardware_smoke(hub_name, timeout)
    except LinkError as exc:
        print(f"SMOKE FAIL: {exc}")
        return 1
    print(f"SMOKE PASS: {candidate.name} connected, bridge READY, PING/PONG received")
    return 0


def _gamepad_diagnostic(once: bool) -> int:
    import pygame

    from .gamepad import GamepadManager

    pygame.init()
    pygame.display.set_mode((1, 1), flags=pygame.HIDDEN)
    gamepad = GamepadManager()
    if gamepad.active is None:
        print("No gamepad found. Pair the Stadia controller in macOS Bluetooth Settings.")
        pygame.quit()
        return 1
    active = gamepad.active
    assert active is not None
    print(
        f"Found: {active.get_name()} "
        f"({active.get_numaxes()} axes, {active.get_numbuttons()} buttons, "
        f"{active.get_numhats()} hats)"
    )
    print("Move left-stick Y and right-stick X; press A to verify STOP. Ctrl-C exits.")
    try:
        while True:
            for event in pygame.event.get():
                gamepad.handle_event(event)
            reading = gamepad.read()
            print(
                f"\rthrottle={reading.throttle:+.2f}  steer={reading.steer:+.2f}  "
                f"stop={'YES' if reading.stop else 'no '}  ",
                end="",
                flush=True,
            )
            if once:
                print()
                return 0
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\nGamepad diagnostic stopped.")
        return 0
    finally:
        pygame.quit()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    hubs = subparsers.add_parser("hubs", help="list nearby advertising Pybricks hubs")
    hubs.add_argument("--scan-timeout", type=float, default=10.0)

    doctor = subparsers.add_parser("doctor", help="check dependencies and discover the hub")
    _add_hub_options(doctor)

    run = subparsers.add_parser("run", help="open the directional control window")
    _add_hub_options(run)
    run.add_argument("--speed", type=int, default=35, help="initial power percent (10-60)")
    run.add_argument(
        "--gamepad-deadzone",
        type=float,
        default=0.10,
        help="ignored stick travel around center (0.0-0.9)",
    )

    gamepad = subparsers.add_parser("gamepad", help="inspect a paired Bluetooth controller")
    gamepad.add_argument("--once", action="store_true", help="print one reading and exit")

    smoke = subparsers.add_parser("smoke", help="run a stopped hardware-in-the-loop check")
    _add_hub_options(smoke)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "hubs":
        return asyncio.run(_list_hubs(args.scan_timeout))
    if args.command == "doctor":
        return asyncio.run(_doctor(args.hub_name, args.scan_timeout))
    if args.command == "smoke":
        return asyncio.run(_smoke(args.hub_name, args.scan_timeout))
    if args.command == "gamepad":
        return _gamepad_diagnostic(args.once)
    if args.command == "run":
        from .ui import MAX_UI_SPEED, MIN_UI_SPEED, run_ui

        if not MIN_UI_SPEED <= args.speed <= MAX_UI_SPEED:
            parser.error(f"--speed must be between {MIN_UI_SPEED} and {MAX_UI_SPEED}")
        if not 0.0 <= args.gamepad_deadzone < 1.0:
            parser.error("--gamepad-deadzone must be at least 0 and less than 1")
        try:
            run_ui(args.hub_name, args.scan_timeout, args.speed, args.gamepad_deadzone)
        except KeyboardInterrupt:
            print("Controller stopped safely.")
        return 0
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
