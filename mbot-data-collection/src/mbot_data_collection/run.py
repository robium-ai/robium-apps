"""Command-line surface."""

from __future__ import annotations

import argparse
from pathlib import Path

from .config import CONFIG_PATH, RobotConfig


def _robot(args: argparse.Namespace) -> RobotConfig:
    """Saved calibration, with any command-line overrides applied on top."""
    robot = RobotConfig.load()
    for field in (
        "port", "baud", "control_hz", "camera_index", "camera_name", "min_pwm",
        "max_pwm", "steer_gain", "stick_deadzone", "throttle_axis", "steer_axis",
    ):
        value = getattr(args, field, None)
        if value is not None:
            setattr(robot, field, value)
    return robot


def cmd_doctor(args: argparse.Namespace) -> int:
    """Check every part of the chain before blaming the robot."""
    import shutil

    from .link import LinkError, MBotLink, find_port

    ok = True

    # Honour the saved settings, so `./app doctor` checks the same path the
    # other commands will actually take.
    chosen = args.port or RobotConfig.load().port
    using_ble = bool(chosen and chosen.lower().startswith("ble"))
    port = chosen or find_port()

    if using_ble:
        print(f"      checking the Bluetooth path ({port})")
    elif port:
        print(f"ok:   serial port {port}")
    else:
        print("FAIL: no mBot serial port found - check the USB cable")
        print("      (for Bluetooth instead, run: ./app doctor --port ble)")
        ok = False

    if shutil.which("arduino-cli"):
        print("ok:   arduino-cli present (needed only to flash firmware)")
    else:
        print("note: arduino-cli missing - 'brew install arduino-cli' before './app flash'")

    if port:
        try:
            with MBotLink(port, baud=args.baud or RobotConfig.load().baud) as link:
                print(f"ok:   firmware responding - {link.banner or link.version()}")
                print(f"      telemetry {link.telemetry()}")
        except LinkError as exc:
            print(f"FAIL: {exc}")
            ok = False

    try:
        from .camera import describe_cameras

        rows = describe_cameras()
        if rows:
            robot = RobotConfig.load()
            mapped = robot.camera_map or {}
            # Names, not positions: the position in this list is not the OpenCV
            # index and drifts between runs, so printing it would invite exactly
            # the confusion the measured map exists to prevent.
            shown = ", ".join(
                f"{name}"
                + (f"(cv{mapped[name]})" if name in mapped else "(unmeasured)")
                for _, name, _ in rows
            )
            print(f"ok:   cameras {shown}")
            picked = robot.camera_name or f"index {robot.camera_index}"
            print(f"      recording would use: {picked}")
            if not mapped:
                print("      run './app cameras --identify' to measure the indices")
        else:
            print("FAIL: no camera delivered a frame - check macOS camera permission")
            ok = False
    except ImportError:
        print("note: opencv not installed - run './app build'")

    try:
        import os

        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        import pygame

        pygame.init()
        pygame.joystick.init()
        count = pygame.joystick.get_count()
        if count:
            names = [pygame.joystick.Joystick(i).get_name() for i in range(count)]
            print(f"ok:   gamepad {names}")
        else:
            print("note: no gamepad attached - the keyboard still drives")
        pygame.quit()
    except ImportError:
        print("note: pygame not installed - run './app build'")

    print("DOCTOR PASS" if ok else "DOCTOR FAIL")
    return 0 if ok else 1


def cmd_flash(args: argparse.Namespace) -> int:
    from .flash import FlashError, flash, flash_isp
    from .link import find_port

    try:
        if args.isp:
            return flash_isp(args.isp, args.isp_port, skip_compile=args.no_compile)

        port = args.port or find_port()
        if port is None:
            print("No mBot serial port found - check the USB cable.")
            return 1
        return flash(port, skip_compile=args.no_compile)
    except FlashError as exc:
        print(f"\nFlashing failed: {exc}\n")
        print("On an mCore this is almost always physical:")
        print("  1. Unplug the Bluetooth / 2.4G module. This is the usual cause:")
        print("     it shares the D0/D1 upload UART, and two drivers on one RX")
        print("     pin corrupt the handshake. Plug it back in when you're done.")
        print("  2. Switch the mBot's power ON (USB alone can brown out the board).")
        print("  3. Try a different USB cable; some are charge-only.")
        print()
        print("If the module is soldered on and cannot be removed, program over")
        print("ICSP instead, which does not use those pins at all:")
        print("  ./app flash --isp usbasp")
        print("  ./app flash --isp arduino-as-isp --isp-port /dev/cu.usbmodemXXXX")
        return 1


def cmd_ping(args: argparse.Namespace) -> int:
    from .link import LinkError, MBotLink

    robot = _robot(args)
    try:
        with MBotLink(robot.port, baud=robot.baud) as link:
            print(link.banner or link.version())
            print(link.telemetry())
            link.beep()
    except LinkError as exc:
        print(f"{exc}")
        return 1
    return 0


def cmd_cameras(args: argparse.Namespace) -> int:
    """List the cameras, so one can be chosen by name instead of by index."""
    from .camera import describe_cameras, identify_cameras

    robot = RobotConfig.load()
    if args.identify:
        print("Opening each camera once to see which index it is.")
        print("A Continuity camera will wake briefly; this is the only step that does.\n")
        mapping = identify_cameras()
        if not mapping:
            print("Could not identify any cameras.")
            return 1
        robot.camera_map = mapping
        robot.save()
        for found, index in sorted(mapping.items(), key=lambda kv: kv[1]):
            print(f"  OpenCV index {index}: {found}")
        print("\nSaved. Pin one with: ./app config --camera-name <name>")
        return 0

    rows = describe_cameras()
    if not rows:
        print("No cameras found.")
        return 1

    mapped = robot.camera_map or {}
    for _, name, continuity in rows:
        where = f"OpenCV index {mapped[name]}" if name in mapped else "index not measured"
        tag = "   (Continuity: a phone)" if continuity else ""
        chosen = "   <- selected" if (
            robot.camera_name and robot.camera_name.lower() in name.lower()
        ) else ""
        print(f"  {name:28} {where}{tag}{chosen}")

    if not mapped:
        print("\nOpenCV's index order differs from the order above, so the")
        print("correspondence has to be measured once:")
        print("  ./app cameras --identify")
    else:
        print("\nPin one with:  ./app config --camera-name <name>")
    return 0


def cmd_gamepad(args: argparse.Namespace) -> int:
    """Show live axis values, so the right axes can be identified rather than guessed.

    macOS presents a gamepad identically over USB and Bluetooth, so this says
    nothing about how it is connected - only which axis moves when you push what.
    """
    import os
    import time

    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    # No window needed for a terminal readout, and the dummy driver keeps this
    # usable over SSH.
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame

    pygame.init()
    pygame.joystick.init()
    if pygame.joystick.get_count() == 0:
        print("No gamepad found.")
        print("  Over USB: check the cable. Over Bluetooth: pair it in System")
        print("  Settings first - macOS shows both the same way once connected.")
        return 1

    stick = pygame.joystick.Joystick(0)
    stick.init()
    robot = _robot(args)
    print(f"{stick.get_name()}: {stick.get_numaxes()} axes, {stick.get_numbuttons()} buttons")
    print(f"currently reading throttle=axis {robot.throttle_axis}, steer=axis {robot.steer_axis}")
    print("Push the sticks. Ctrl-C to stop.\n")

    try:
        while True:
            pygame.event.pump()
            axes = [stick.get_axis(i) for i in range(stick.get_numaxes())]
            shown = "  ".join(f"{i}:{v:+0.2f}" for i, v in enumerate(axes))
            loudest = max(range(len(axes)), key=lambda i: abs(axes[i])) if axes else -1
            marker = f"   <- axis {loudest} is moving most" if axes and abs(axes[loudest]) > 0.3 else ""
            print(f"\r{shown}{marker}   ", end="", flush=True)
            time.sleep(0.08)
    except KeyboardInterrupt:
        print("\n\nSet them with:  ./app drive --throttle-axis N --steer-axis N")
    return 0


def cmd_calibrate(args: argparse.Namespace) -> int:
    from .drive import calibrate, measure_floor
    from .link import LinkError

    try:
        if args.floor:
            return measure_floor(_robot(args))
        return calibrate(_robot(args))
    except LinkError as exc:
        print(f"{exc}")
        return 1


def cmd_drive(args: argparse.Namespace) -> int:
    from .drive import drive
    from .link import LinkError

    try:
        return drive(_robot(args), args.window, args.keyboard, args.no_camera)
    except LinkError as exc:
        print(f"{exc}")
        return 1


def cmd_record(args: argparse.Namespace) -> int:
    from .record import RecordConfig, record

    root = Path(args.root) if args.root else Path("outputs/datasets") / args.repo_id.split("/")[-1]
    return record(
        RecordConfig(
            repo_id=args.repo_id,
            root=root,
            task=args.task,
            episodes=args.episodes,
            window=args.window,
            push_to_hub=args.push_to_hub,
            private=args.private,
            resume=args.resume,
            prefer_keyboard=args.keyboard,
        ),
        _robot(args),
    )


def cmd_push(args: argparse.Namespace) -> int:
    from .record import push

    root = Path(args.root) if args.root else Path("outputs/datasets") / args.repo_id.split("/")[-1]
    return push(args.repo_id, root, private=args.private)


def cmd_config(args: argparse.Namespace) -> int:
    """Show the saved settings, or change them.

    Any hardware option given here is written to disk, so a choice like "this
    robot is on Bluetooth" is made once instead of on every command line.
    """
    robot = RobotConfig.load()
    changed = {
        field: getattr(args, field)
        for field in (
            "port", "baud", "control_hz", "camera_index", "camera_name", "min_pwm",
            "max_pwm", "steer_gain", "stick_deadzone", "throttle_axis", "steer_axis",
        )
        if getattr(args, field, None) is not None
    }
    if changed:
        for field, value in changed.items():
            setattr(robot, field, value)
        robot.save()
        print(f"saved to {CONFIG_PATH}")
    else:
        print(f"{CONFIG_PATH}{'' if CONFIG_PATH.exists() else '  (defaults; not saved yet)'}")

    for key, value in vars(robot).items():
        marker = "  <-- changed" if key in changed else ""
        print(f"  {key:<15} {value}{marker}")
    if not changed:
        print("\nChange one with, for example:  ./app config --port ble")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mbot-data-collection",
        description="Teleoperate a Makeblock mBot and record camera-and-action episodes.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def hardware(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--port",
            help="Serial port. Autodetected over USB; required for Bluetooth, "
            "where it is the paired module's port (e.g. /dev/cu.Makeblock-XXXX)",
        )
        p.add_argument("--baud", type=int, help="Wire rate (default 115200)")
        p.add_argument(
            "--control-hz",
            type=float,
            help="Control rate, and the recorded fps (default 20). Worth raising "
            "over USB; over Bluetooth the connection interval caps the benefit",
        )
        p.add_argument(
            "--stick-deadzone",
            type=float,
            help="Stick travel treated as centred, 0-0.9 (default 0.12)",
        )
        p.add_argument("--throttle-axis", type=int, help="Gamepad axis for throttle")
        p.add_argument("--steer-axis", type=int, help="Gamepad axis for steer")
        p.add_argument("--camera-index", type=int, help="Webcam index")
        p.add_argument(
            "--camera-name",
            help="Webcam by name, e.g. I930. Beats --camera-index, and survives "
            "macOS renumbering cameras when a phone joins over Continuity",
        )
        p.add_argument("--min-pwm", type=int, help="Duty at which the wheels start turning")
        p.add_argument("--max-pwm", type=int, help="Duty at full deflection")
        p.add_argument(
            "--steer-gain",
            type=float,
            help="How much stick steer to use, 0-1. Lower is calmer (default 0.45)",
        )

    doctor = sub.add_parser("doctor", help="Check port, firmware, camera, gamepad")
    doctor.add_argument("--port")
    doctor.add_argument("--baud", type=int, help="Wire rate to try (default 115200)")
    doctor.set_defaults(func=cmd_doctor)

    flash_p = sub.add_parser("flash", help="Compile and upload the bridge firmware")
    flash_p.add_argument("--port")
    flash_p.add_argument("--no-compile", action="store_true", help="Upload the existing build")
    flash_p.add_argument(
        "--isp",
        choices=["arduino-as-isp", "usbasp", "usbtiny"],
        help="Program over ICSP instead of the serial port (for a soldered-on BT module)",
    )
    flash_p.add_argument("--isp-port", help="Serial port of the Arduino acting as programmer")
    flash_p.set_defaults(func=cmd_flash)

    ping = sub.add_parser("ping", help="Talk to the firmware and beep")
    hardware(ping)
    ping.set_defaults(func=cmd_ping)

    cams = sub.add_parser("cameras", help="List cameras with their names")
    cams.add_argument(
        "--identify",
        action="store_true",
        help="Measure which OpenCV index opens which camera, and remember it",
    )
    cams.set_defaults(func=cmd_cameras)

    pad = sub.add_parser("gamepad", help="Show live gamepad axis values")
    hardware(pad)
    pad.set_defaults(func=cmd_gamepad)

    calib = sub.add_parser("calibrate", help="Learn which motor is which, and which way")
    hardware(calib)
    calib.add_argument(
        "--floor",
        action="store_true",
        help="Instead, measure the lowest duty that actually turns the wheels (min_pwm)",
    )
    calib.set_defaults(func=cmd_calibrate)

    drive_p = sub.add_parser("drive", help="Drive with the arrow keys or a gamepad")
    hardware(drive_p)
    drive_p.add_argument("--window", type=int, default=720, help="Preview width")
    drive_p.add_argument("--keyboard", action="store_true", help="Ignore any gamepad")
    drive_p.add_argument("--no-camera", action="store_true", help="Drive without the webcam")
    drive_p.set_defaults(func=cmd_drive)

    rec = sub.add_parser("record", help="Record teleoperated episodes to a dataset")
    hardware(rec)
    rec.add_argument("--repo-id", required=True, help="Hub dataset id, e.g. you/mbot-drive")
    rec.add_argument("--task", default="drive the robot to the goal", help="Language instruction")
    rec.add_argument("--episodes", type=int, default=5)
    rec.add_argument("--root", help="Local dataset directory (default: outputs/datasets/<name>)")
    rec.add_argument("--window", type=int, default=720)
    rec.add_argument("--keyboard", action="store_true", help="Ignore any gamepad")
    rec.add_argument("--push-to-hub", action="store_true", help="Upload when finished")
    rec.add_argument("--private", action="store_true")
    rec.add_argument("--resume", action="store_true", help="Append to an existing dataset")
    rec.set_defaults(func=cmd_record)

    push_p = sub.add_parser("push", help="Upload a recorded dataset to the Hub")
    push_p.add_argument("--repo-id", required=True)
    push_p.add_argument("--root")
    push_p.add_argument("--private", action="store_true")
    push_p.set_defaults(func=cmd_push)

    cfg = sub.add_parser("config", help="Show or change the saved settings")
    hardware(cfg)
    cfg.set_defaults(func=cmd_config)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
