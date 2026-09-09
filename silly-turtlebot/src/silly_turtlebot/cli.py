"""Command-line interface for the first Silly TurtleBot slice."""

from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import os
from pathlib import Path

from .config import MODEL
from .demo import run_mock_sock_mission
from .fake_robot import FakeRobot
from .guard import MissionGuard
from .live_agent import GeminiRoboticsLiveAgent
from .mission_server import serve_missions
from .rest_robot import RestRobot
from .tools import function_declarations


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="silly-turtlebot")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("demo", help="run the deterministic fake sock mission")
    commands.add_parser("doctor", help="check local and optional live prerequisites")
    commands.add_parser("tools", help="print model-visible tool names")

    live = commands.add_parser(
        "live", help="connect ER 2 Streaming to fake or ROS robot"
    )
    live.add_argument("--text", help="text instruction to send")
    live.add_argument("--image", type=Path, help="optional JPEG scene frame")
    live.add_argument("--audio", type=Path, help="optional raw 16 kHz s16le mono PCM")
    live.add_argument("--timeout", type=float, default=240.0)
    live.add_argument(
        "--robot-url",
        default=os.environ.get("SILLY_ROBOT_URL"),
        help="robot bridge URL; omit for the fake robot",
    )
    live.add_argument(
        "--camera-source",
        choices=("primary", "secondary"),
        default="primary",
        help="ROS camera to send to Gemini in robot mode",
    )
    live.add_argument(
        "--camera-url",
        default=os.environ.get("SILLY_CAMERA_URL"),
        help="optional external camera server URL, for example the Orin OAK-D",
    )

    robot_doctor = commands.add_parser(
        "robot-doctor", help="check the ROS bridge, Nav2 actions, and cameras"
    )
    robot_doctor.add_argument("--robot-url", default=os.environ.get("SILLY_ROBOT_URL"))
    robot_doctor.add_argument(
        "--camera-url", default=os.environ.get("SILLY_CAMERA_URL")
    )

    camera = commands.add_parser("camera", help="save one ROS camera JPEG")
    camera.add_argument("--robot-url", default=os.environ.get("SILLY_ROBOT_URL"))
    camera.add_argument("--camera-url", default=os.environ.get("SILLY_CAMERA_URL"))
    camera.add_argument(
        "--camera-source", choices=("primary", "secondary"), default="primary"
    )
    camera.add_argument("--output", type=Path, default=Path("scene.jpg"))

    serve = commands.add_parser(
        "serve", help="serve guarded Gemini missions for the local demo console"
    )
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8090)
    return parser


def _doctor() -> int:
    checks = []
    checks.append(("google-genai", importlib.metadata.version("google-genai"), True))
    checks.append(("model", MODEL, True))
    key_present = bool(os.environ.get("GEMINI_API_KEY"))
    checks.append(
        (
            "GEMINI_API_KEY",
            "present" if key_present else "missing (only required for ./app live)",
            True,
        )
    )
    for name, detail, passed in checks:
        print(f"{'PASS' if passed else 'FAIL'} {name}: {detail}")
    print("PASS motion boundary: Gemini has semantic tools only; no /cmd_vel tool")
    return 0


def _live(args: argparse.Namespace) -> int:
    for path in (args.image, args.audio):
        if path is not None and not path.is_file():
            raise SystemExit(f"input file does not exist: {path}")
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise SystemExit("GEMINI_API_KEY is required for ./app live")
    adapter = (
        RestRobot(
            args.robot_url,
            camera_source=args.camera_source,
            camera_url=args.camera_url,
        )
        if args.robot_url
        else FakeRobot()
    )
    image_bytes = None
    if args.robot_url:
        print("MODE: LIVE GEMINI + ROS 2/NAV2 ROBOT")
        if args.image is None:
            image_bytes = adapter.capture_camera_frame()
            if image_bytes is None:
                print(f"WARN no fresh {args.camera_source} camera frame; continuing")
    else:
        print("MODE: LIVE GEMINI + FAKE ROBOT (no ROS, Nav2, or motor connection)")
    guard = MissionGuard(adapter)
    agent = GeminiRoboticsLiveAgent(key, guard)
    asyncio.run(
        agent.run_once(
            text=args.text,
            image_path=args.image,
            audio_path=args.audio,
            image_bytes=image_bytes,
            timeout_s=args.timeout,
        )
    )
    print(f"Live turn complete: {len(guard.events)} guarded tool call(s)")
    return 0


def _require_robot_url(value: str | None) -> str:
    if not value:
        raise SystemExit(
            "set SILLY_ROBOT_URL or pass --robot-url; use an SSH tunnel to the bridge"
        )
    return value


def _robot_doctor(args: argparse.Namespace) -> int:
    robot = RestRobot(
        _require_robot_url(args.robot_url),
        camera_url=args.camera_url,
    )
    health = robot.health()
    print(f"robot bridge: {health.get('status', 'failed')}")
    print(f"Nav2 navigate_to_pose: {health.get('navigate_to_pose', False)}")
    print(f"Nav2 drive_on_heading: {health.get('drive_on_heading', False)}")
    print(f"Nav2 spin: {health.get('spin', False)}")
    print(f"configured locations: {', '.join(health.get('locations', [])) or 'none'}")
    cameras = health.get("cameras", {})
    for name in ("primary", "secondary"):
        state = cameras.get(name, {})
        print(
            f"camera {name}: topic={state.get('topic') or 'disabled'} "
            f"fresh={state.get('fresh', False)}"
        )
    ready = (
        health.get("status") == "ok"
        and health.get("navigate_to_pose") is True
        and health.get("drive_on_heading") is True
        and bool(health.get("locations"))
        and any(item.get("fresh") for item in cameras.values())
    )
    return 0 if ready else 1


def _camera(args: argparse.Namespace) -> int:
    robot = RestRobot(
        _require_robot_url(args.robot_url),
        camera_source=args.camera_source,
        camera_url=args.camera_url,
    )
    frame = robot.capture_camera_frame()
    if frame is None:
        raise SystemExit(f"no fresh {args.camera_source} camera frame")
    args.output.write_bytes(frame)
    print(f"saved {args.camera_source} camera frame to {args.output}")
    return 0


def main() -> int:
    args = _parser().parse_args()
    if args.command == "demo":
        guard = run_mock_sock_mission()
        if len(guard.events) != 6:
            return 1
        print("SILLY TURTLEBOT MOCK PASS")
        return 0
    if args.command == "doctor":
        return _doctor()
    if args.command == "tools":
        for declaration in function_declarations():
            print(declaration["name"])
        return 0
    if args.command == "live":
        return _live(args)
    if args.command == "robot-doctor":
        return _robot_doctor(args)
    if args.command == "camera":
        return _camera(args)
    if args.command == "serve":
        return serve_missions(host=args.host, port=args.port)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
