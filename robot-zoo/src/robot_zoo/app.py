"""Robot Zoo command-line entry points and bounded physics checks."""

from __future__ import annotations

import argparse
import base64
import math
import threading
from multiprocessing.connection import Client

import numpy as np

from .controllers import ROBOTS, create_controller, prefetch_models
from .bridge import serve_commands
from .simulation import SimulationManager


def run_application(initial_robot: str, *, server_port: int | None = None) -> int:
    from .native_app import run_native_application

    return run_native_application(initial_robot, server_port=server_port)


def run_worker(host: str, port: int, authkey: str, robot: str) -> int:
    """Run MuJoCo and receive commands from the native controller process."""
    key = base64.urlsafe_b64decode(authkey.encode("ascii"))
    connection = Client((host, port), authkey=key)
    manager = SimulationManager(robot)
    thread = threading.Thread(
        target=serve_commands,
        args=(manager, connection),
        name="controller-bridge",
        daemon=True,
    )
    thread.start()
    try:
        return manager.run()
    finally:
        manager.shutdown()


def check_models(seconds: float = 3.0) -> int:
    """Bounded physics proof for the three behaviors the app advertises."""
    results: list[str] = []

    panda = create_controller("panda")
    hand_id = panda.model.body("hand").id
    start_hand = panda.data.xpos[hand_id].copy()
    for _ in range(math.ceil(seconds / panda.model.opt.timestep)):
        panda.step()
    hand_distance = float(np.linalg.norm(panda.data.xpos[hand_id] - start_hand))
    if hand_distance < 0.025:
        raise RuntimeError(f"Panda hand barely moved: {hand_distance:.4f} m")
    results.append(f"Panda hand moved {hand_distance:.3f} m")

    turtlebot = create_controller("turtlebot3")
    turtlebot.set_motion(1., 0., 1.)
    for _ in range(math.ceil(seconds / turtlebot.model.opt.timestep)):
        turtlebot.step()
    travel = float(turtlebot.data.qpos[0])
    if travel < .1 or not np.isfinite(turtlebot.data.qpos).all():
        raise RuntimeError(f"TurtleBot3 failed to drive forward: {travel:.3f} m")
    turtlebot.stop()
    for _ in range(round(1 / turtlebot.model.opt.timestep)):
        turtlebot.step()
    if np.linalg.norm(turtlebot.data.qvel[:6]) > .02:
        raise RuntimeError("TurtleBot3 did not settle after Stop")
    results.append(f"TurtleBot3 drove {travel:.3f} m and stopped")

    go2 = create_controller("go2")
    go2.set_motion(1., 0., .7, vy=.5)
    for _ in range(math.ceil(max(seconds, 5.0) / go2.model.opt.timestep)):
        go2.step()
    base_height = float(go2.data.qpos[2])
    upright = abs(float(go2.data.qpos[3]))
    if base_height < 0.20 or upright < 0.90:
        raise RuntimeError(
            f"Go2 lost posture: base z={base_height:.3f}, upright={upright:.3f}"
        )
    if not np.isfinite(go2.data.qpos).all() or not np.isfinite(go2.data.ctrl).all():
        raise RuntimeError("Go2 state or controls contain non-finite values")
    travel = float(np.linalg.norm(go2.data.qpos[:2]))
    if travel < .5:
        raise RuntimeError(f"Go2 barely moved: {travel:.3f} m")
    go2.stop()
    for _ in range(round(2.5 / go2.model.opt.timestep)):
        go2.step()
    if np.linalg.norm(go2.data.qvel[:3]) > .10:
        raise RuntimeError("Go2 did not settle after Stop")
    results.append(f"Go2 walked {travel:.3f} m, stayed upright, and stopped")

    for result in results:
        print(f"ok: {result}")
    print("ROBOT ZOO CHECK PASS")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="robot-zoo",
        description="Native controls for three robots in MuJoCo's native viewer.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Open the controller and native MuJoCo viewer")
    run.add_argument("--robot", choices=tuple(ROBOTS), default="panda")
    run.add_argument("--port", type=int)
    run.set_defaults(
        func=lambda args: run_application(
            args.robot,
            server_port=args.port,
        )
    )

    viewer = sub.add_parser("viewer", help="Open only the native MuJoCo viewer")
    viewer.add_argument("--robot", choices=tuple(ROBOTS), default="panda")
    viewer.set_defaults(func=lambda args: SimulationManager(args.robot).run())

    check = sub.add_parser("check", help="Run bounded headless physics checks")
    check.add_argument("--seconds", type=float, default=3.0)
    check.set_defaults(func=lambda args: check_models(args.seconds))

    prefetch = sub.add_parser("prefetch", help="Cache and compile the robot models")
    prefetch.set_defaults(func=lambda _args: prefetch_models() or 0)

    worker = sub.add_parser("worker", help=argparse.SUPPRESS)
    worker.add_argument("--host", required=True)
    worker.add_argument("--port", required=True, type=int)
    worker.add_argument("--authkey", required=True)
    worker.add_argument("--robot", choices=tuple(ROBOTS), required=True)
    worker.set_defaults(
        func=lambda args: run_worker(
            args.host, args.port, args.authkey, args.robot
        )
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
