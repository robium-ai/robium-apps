"""Local HTTP boundary between the Lichtblick UI and the guarded Gemini agent."""

from __future__ import annotations

import asyncio
import json
import os
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .guard import MissionGuard
from .live_agent import GeminiRoboticsLiveAgent
from .rest_robot import RestRobot


MAX_REQUEST_BYTES = 16 * 1024
MAX_INSTRUCTION_CHARS = 2000


class MissionService:
    def __init__(self, api_key: str, robot_url: str, camera_url: str | None = None):
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required by the mission service")
        self.api_key = api_key
        self.robot_url = robot_url
        self.camera_url = camera_url
        self._mission_lock = threading.Lock()

    def health(self) -> dict[str, Any]:
        robot = RestRobot(self.robot_url, camera_url=self.camera_url)
        health = robot.health()
        return {
            "status": "ok" if health.get("status") == "ok" else "starting",
            "robot": health,
        }

    def run(self, instruction: str, camera_source: str = "primary") -> dict[str, Any]:
        instruction = instruction.strip()
        if not instruction:
            raise ValueError("instruction must not be empty")
        if len(instruction) > MAX_INSTRUCTION_CHARS:
            raise ValueError(
                f"instruction exceeds {MAX_INSTRUCTION_CHARS} characters"
            )
        if camera_source not in {"primary", "secondary"}:
            raise ValueError("camera_source must be primary or secondary")
        if not self._mission_lock.acquire(blocking=False):
            raise RuntimeError("another mission is already running")
        try:
            robot = RestRobot(
                self.robot_url,
                camera_source=camera_source,
                camera_url=self.camera_url,
            )
            frame = robot.capture_camera_frame()
            guard = MissionGuard(robot)
            agent = GeminiRoboticsLiveAgent(self.api_key, guard)
            text_parts = asyncio.run(
                agent.run_once(
                    text=instruction,
                    image_bytes=frame,
                    timeout_s=240.0,
                )
            )
            response = "".join(text_parts).strip()
            if not response:
                spoken = [
                    event.arguments["message"]
                    for event in guard.events
                    if event.name == "speak" and "message" in event.arguments
                ]
                response = spoken[-1] if spoken else "Mission completed."
            return {
                "status": "succeeded",
                "response": response,
                "tool_calls": [
                    {
                        "name": event.name,
                        "arguments": event.arguments,
                        "result": event.result,
                    }
                    for event in guard.events
                ],
            }
        finally:
            self._mission_lock.release()

    def camera(self) -> bytes | None:
        """Return the current primary view without exposing the camera host."""
        return RestRobot(
            self.robot_url,
            camera_url=self.camera_url,
        ).capture_camera_frame()

    def stop(self) -> dict[str, Any]:
        return RestRobot(self.robot_url).stop("Stopped from Lichtblick mission control")


def make_handler(service: MissionService):
    class Handler(BaseHTTPRequestHandler):
        def _jpeg_response(self, status: int, payload: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def _json_response(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _request_json(self) -> dict[str, Any]:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError as error:
                raise ValueError("invalid Content-Length") from error
            if length <= 0 or length > MAX_REQUEST_BYTES:
                raise ValueError("request body size is invalid")
            try:
                value = json.loads(self.rfile.read(length))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ValueError("request body must be JSON") from error
            if not isinstance(value, dict):
                raise ValueError("request body must be a JSON object")
            return value

        def do_GET(self) -> None:
            if self.path == "/v1/camera":
                frame = service.camera()
                if frame is None:
                    self._json_response(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        {"status": "failed", "reason": "no fresh camera frame"},
                    )
                else:
                    self._jpeg_response(HTTPStatus.OK, frame)
                return
            if self.path != "/v1/health":
                self._json_response(HTTPStatus.NOT_FOUND, {"status": "not_found"})
                return
            payload = service.health()
            status = (
                HTTPStatus.OK
                if payload["status"] == "ok"
                else HTTPStatus.SERVICE_UNAVAILABLE
            )
            self._json_response(status, payload)

        def do_POST(self) -> None:
            try:
                if self.path == "/v1/missions":
                    body = self._request_json()
                    payload = service.run(
                        str(body.get("instruction", "")),
                        str(body.get("camera_source", "primary")),
                    )
                    self._json_response(HTTPStatus.OK, payload)
                    return
                if self.path == "/v1/stop":
                    self._json_response(HTTPStatus.OK, service.stop())
                    return
                self._json_response(HTTPStatus.NOT_FOUND, {"status": "not_found"})
            except ValueError as error:
                self._json_response(
                    HTTPStatus.BAD_REQUEST,
                    {"status": "rejected", "reason": str(error)},
                )
            except RuntimeError as error:
                self._json_response(
                    HTTPStatus.CONFLICT,
                    {"status": "busy", "reason": str(error)},
                )
            except Exception as error:  # noqa: BLE001 - HTTP failure boundary.
                self._json_response(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"status": "failed", "reason": str(error)},
                )

        def log_message(self, format: str, *args: Any) -> None:
            print(f"mission_api: {format % args}", flush=True)

    return Handler


def serve_missions(host: str = "127.0.0.1", port: int = 8090) -> int:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    robot_url = os.environ.get("SILLY_ROBOT_URL", "http://127.0.0.1:8088")
    camera_url = os.environ.get("SILLY_CAMERA_URL")
    service = MissionService(
        api_key=api_key,
        robot_url=robot_url,
        camera_url=camera_url,
    )
    server = ThreadingHTTPServer((host, port), make_handler(service))
    print(f"Mission API: http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
