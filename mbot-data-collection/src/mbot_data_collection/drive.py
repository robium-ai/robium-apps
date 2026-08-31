"""Teleoperation, and the calibration that has to happen before it means much.

The drive loop is the reference implementation of one control tick, and both
recording and any later policy rollout are expected to reuse its shape: read an
action, mix it to wheels, apply the chassis wiring, send one command, draw. It
sends a command every tick even when the action is zero, because the board's
watchdog reads silence as "the host is gone" and stops the wheels.
"""

from __future__ import annotations

import time

import numpy as np

from .config import CONTROL_HZ, RobotConfig
from .link import MBotLink


def _drain_events() -> tuple[bool, set[int]]:
    """Pump pygame's queue once. Returns (still running, keys pressed now)."""
    import pygame

    running = True
    pressed = set()
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            pressed.add(event.key)
            if event.key == pygame.K_q:
                running = False
    return running, pressed


def drive(config: RobotConfig, window: int, prefer_keyboard: bool, no_camera: bool) -> int:
    """Drive the robot by hand, watching the camera."""
    # .ui first: it silences pygame's greeting before pygame is imported.
    from .ui import Teleop, Viewer

    import pygame

    from .camera import Camera

    period = 1.0 / config.control_hz
    camera = None if no_camera else Camera(config.camera_index, config.camera_width, config.camera_height, config.camera_name, config.camera_map)
    viewer = Viewer(width=window, title="mbot - drive")
    teleop = Teleop(
        throttle_axis=config.throttle_axis,
        steer_axis=config.steer_axis,
        prefer_keyboard=prefer_keyboard,
        deadzone=config.stick_deadzone,
    )

    print(f"Driving with {teleop.source}.")
    print("  arrows / WASD   throttle and steer")
    print("  space           stop the wheels now")
    print("  q               quit")

    try:
        if camera is not None:
            camera.open()
        with MBotLink(config.port, watchdog_ms=config.watchdog_ms, baud=config.baud) as link:
            print(f"  board: {link.banner}")
            link.beep(988, 90)
            blank = np.zeros((config.camera_height, config.camera_width, 3), dtype=np.uint8)

            running = True
            while running:
                started = time.monotonic()
                running, pressed = _drain_events()

                action = teleop.read(period)
                if pygame.K_SPACE in pressed:
                    teleop.reset()  # release the ramp, not just this tick's output
                    action = np.zeros(2)

                left, right = config.wheels(action)
                m1, m2 = config.to_pwm(left, right)
                link.stream_pwm(m1, m2)

                frame = camera.latest() if camera is not None else None
                viewer.show(
                    frame if frame is not None else blank,
                    [
                        f"throttle {action[0]:+0.2f}   steer {action[1]:+0.2f}",
                        f"wheels L {left:+0.2f} R {right:+0.2f}   ->   M1 {m1:+4d}  M2 {m2:+4d}",
                        teleop.source,
                    ],
                )

                elapsed = time.monotonic() - started
                if elapsed < period:
                    time.sleep(period - elapsed)
    except KeyboardInterrupt:
        pass
    finally:
        teleop.close()
        viewer.close()
        if camera is not None:
            camera.close()
    return 0


def bisect_floor(moves, low: int = 10, high: int = 200, tolerance: int = 4) -> int:
    """Smallest duty that still turns the wheels, given a moves(duty) oracle.

    Separated from the prompting so the search is testable without a robot, and
    a bisection because each probe costs a human answering a question: eight
    questions linearly becomes five, and each one is a clearly different speed
    rather than a barely distinguishable neighbour.
    """
    if not moves(high):
        raise RuntimeError(f"the wheels did not turn even at duty {high}")
    while high - low > tolerance:
        mid = (low + high) // 2
        if moves(mid):
            high = mid
        else:
            low = mid
    return high


def measure_floor(config: RobotConfig) -> int:
    """Find the duty at which this chassis actually starts moving.

    `min_pwm` decides how slowly the robot can be driven at all, and a guessed
    value is the reason a slow robot still feels twitchy: set too high, the
    gentlest touch of the stick already commands most of the speed range, and
    every demonstration is recorded near full tilt.
    """
    print("This spins both wheels at increasing speeds. Lift the robot first.")
    if input("Ready? [y/N] ").strip().lower() not in {"y", "yes"}:
        return 1

    with MBotLink(config.port, watchdog_ms=0, baud=config.baud) as link:
        print(f"  board: {link.banner}\n")

        def moves(duty: int) -> bool:
            link.drive_pwm(duty, duty)
            time.sleep(1.0)
            link.stop()
            return input(f"  duty {duty:3d}: did the wheels turn? [y/N] ").strip().lower() in {"y", "yes"}

        try:
            floor = bisect_floor(moves)
        except RuntimeError as exc:
            print(f"\n{exc}. Check the battery and that the wheels are free.")
            return 1

    config.min_pwm = floor
    config.save()
    print(f"\nSaved min_pwm = {floor} (was a guess before).")
    if floor < 60:
        span = config.max_pwm - floor
        print(f"  That frees the range {floor}-{config.max_pwm}, so the stick now has")
        print(f"  {span} points of travel to work with instead of {config.max_pwm - 60}.")
    return 0


def calibrate(config: RobotConfig) -> int:
    """Discover the wiring by moving one motor at a time and asking what happened.

    Which motor is on the left, and which way each one turns, are facts about
    how this chassis was assembled. Guessing them produces a robot that steers
    backwards, and worse, a dataset in which "turn left" means two different
    things on two different days.
    """
    print("Calibration moves the wheels. Lift the robot off the table first.")
    if input("Ready? [y/N] ").strip().lower() not in {"y", "yes"}:
        return 1

    pulse = max(config.min_pwm + 40, 120)

    def ask(question: str) -> bool:
        return input(f"{question} [y/N] ").strip().lower() in {"y", "yes"}

    with MBotLink(config.port, watchdog_ms=0, baud=config.baud) as link:
        print(f"  board: {link.banner}")

        observed = {}
        for name, m1, m2 in (("M1", pulse, 0), ("M2", 0, pulse)):
            input(f"\nAbout to spin {name}. Press enter to watch it.")
            # Confirmed, not streamed: a dropped command here would have the
            # human answering questions about a wheel that never moved.
            link.drive_pwm(m1, m2)
            time.sleep(1.2)
            link.stop()
            observed[name] = {
                "left": ask(f"  Was that the LEFT wheel?"),
                "forward": ask(f"  Did it turn FORWARD?"),
            }

    if observed["M1"]["left"] == observed["M2"]["left"]:
        print("\nBoth answers named the same side; nothing was learned. Try again.")
        return 1

    # The firmware always calls its motors M1 and M2. Which of those is the
    # left wheel, and which way each turns, is what we just measured.
    config.swap_motors = not observed["M1"]["left"]
    left_motor = "M1" if observed["M1"]["left"] else "M2"
    right_motor = "M2" if left_motor == "M1" else "M1"
    config.invert_left = not observed[left_motor]["forward"]
    config.invert_right = not observed[right_motor]["forward"]
    config.save()

    print(f"\nSaved: left wheel is {left_motor}")
    print(f"  swap_motors  {config.swap_motors}")
    print(f"  invert_left  {config.invert_left}")
    print(f"  invert_right {config.invert_right}")
    print("\nCheck it with './app drive' - forward should go forward.")
    return 0
