"""Local HTTP boundary between the Lichtblick UI and the guarded Gemini agent."""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import threading
import time
import uuid
from collections import OrderedDict, deque
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib import request as urllib_request
from urllib.parse import urlsplit

from .guard import MissionGuard
from .live_agent import PersistentGeminiSession
from .rest_robot import RestRobot


MAX_REQUEST_BYTES = 16 * 1024
MAX_INSTRUCTION_CHARS = 2000
MAX_EVENTS_PER_MISSION = 512
MAX_RETAINED_MISSIONS = 16
DEFAULT_BROWSER_CAMERA_FPS = 8.0
TERMINAL_STATES = {"completed", "stopped", "failed"}
TERMINAL_EVENT_TYPES = {
    "mission.completed",
    "mission.stopped",
    "mission.failed",
}


def _timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


class MissionService:
    def __init__(
        self,
        api_key: str,
        robot_url: str,
        camera_url: str | None = None,
        tts_url: str | None = None,
        *,
        session_factory: Any = PersistentGeminiSession,
        robot_factory: Any = RestRobot,
        camera_interval_s: float = 1.0,
        heartbeat_idle_s: float = 1.0,
        browser_camera_fps: float = DEFAULT_BROWSER_CAMERA_FPS,
    ):
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required by the mission service")
        self.robot_url = robot_url
        self.camera_url = camera_url
        self.tts_url = tts_url
        if not 1.0 <= browser_camera_fps <= 12.0:
            raise ValueError("browser camera FPS must be between 1 and 12")
        self.browser_camera_interval_s = 1.0 / browser_camera_fps
        self.robot = robot_factory(
            robot_url,
            camera_url=camera_url,
            tts_url=tts_url,
        )
        self._camera_robot = robot_factory(
            robot_url,
            camera_url=camera_url,
        )
        self.guard = MissionGuard(self.robot)

        self._condition = threading.Condition(threading.RLock())
        self._active_mission_id: str | None = None
        self._mission_states: OrderedDict[str, str] = OrderedDict()
        self._events: OrderedDict[str, deque[dict[str, Any]]] = OrderedDict()
        self._last_event_sequence = 0
        self._closed = False

        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(
            target=self._run_loop,
            name="silly-turtlebot-gemini",
            daemon=True,
        )
        self._loop_thread.start()
        self.session = session_factory(
            api_key,
            self.guard,
            self._handle_session_event,
            camera_interval_s=camera_interval_s,
            heartbeat_idle_s=heartbeat_idle_s,
        )

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()
        pending = asyncio.all_tasks(self._loop)
        for task in pending:
            task.cancel()
        if pending:
            self._loop.run_until_complete(
                asyncio.gather(*pending, return_exceptions=True)
            )
        self._loop.close()

    @staticmethod
    def _validate_instruction(instruction: str, camera_source: str) -> str:
        instruction = instruction.strip()
        if not instruction:
            raise ValueError("instruction must not be empty")
        if len(instruction) > MAX_INSTRUCTION_CHARS:
            raise ValueError(
                f"instruction exceeds {MAX_INSTRUCTION_CHARS} characters"
            )
        if camera_source not in {"primary", "secondary"}:
            raise ValueError("camera_source must be primary or secondary")
        return instruction

    def _append_event_locked(
        self,
        mission_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._last_event_sequence += 1
        event = {
            "seq": self._last_event_sequence,
            "timestamp": _timestamp(),
            "mission_id": mission_id,
            "type": event_type,
            "payload": payload or {},
        }
        journal = self._events.setdefault(mission_id, deque())
        journal.append(event)
        self._trim_journal(journal)
        self._condition.notify_all()
        return event

    @staticmethod
    def _trim_journal(journal: deque[dict[str, Any]]) -> None:
        while len(journal) > MAX_EVENTS_PER_MISSION:
            removable = next(
                (
                    index
                    for index, event in enumerate(journal)
                    if event["type"]
                    not in {
                        "tool.finished",
                        "tool.rejected",
                        "tool.response.sent",
                        *TERMINAL_EVENT_TYPES,
                    }
                ),
                None,
            )
            if removable is None:
                journal.popleft()
            else:
                del journal[removable]

    def _prune_missions_locked(self) -> None:
        while len(self._mission_states) > MAX_RETAINED_MISSIONS:
            oldest, state = next(iter(self._mission_states.items()))
            if oldest == self._active_mission_id or state not in TERMINAL_STATES:
                return
            self._mission_states.pop(oldest, None)
            self._events.pop(oldest, None)

    def _handle_session_event(
        self,
        mission_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        with self._condition:
            state = self._mission_states.get(mission_id)
            if state is None or state in TERMINAL_STATES:
                return
            if event_type == "input.sent" and state == "accepted":
                self._mission_states[mission_id] = "running"
            elif event_type in TERMINAL_EVENT_TYPES:
                terminal = event_type.removeprefix("mission.")
                self._mission_states[mission_id] = terminal
                if self._active_mission_id == mission_id:
                    self._active_mission_id = None
            self._append_event_locked(mission_id, event_type, payload)

    def _submission_done(
        self,
        mission_id: str,
        future: concurrent.futures.Future[Any],
    ) -> None:
        try:
            future.result()
        except Exception as error:  # noqa: BLE001 - background submission boundary.
            with self._condition:
                if self._mission_states.get(mission_id) in TERMINAL_STATES:
                    return
                self._mission_states[mission_id] = "failed"
                if self._active_mission_id == mission_id:
                    self._active_mission_id = None
                self._append_event_locked(
                    mission_id,
                    "mission.failed",
                    {"reason": f"could not submit instruction: {error}"},
                )

    def health(self) -> dict[str, Any]:
        health = self.robot.health()
        session = self.session.health_snapshot()
        with self._condition:
            mission_id = self._active_mission_id
            mission_state = (
                self._mission_states.get(mission_id) if mission_id is not None else "idle"
            )
            last_sequence = self._last_event_sequence
        return {
            "status": "ok" if health.get("status") == "ok" else "starting",
            "robot": health,
            "gemini_session": session,
            "mission": {
                "active_mission_id": mission_id,
                "state": mission_state,
            },
            "last_event_sequence": last_sequence,
            "last_camera_frame_age_s": session["last_camera_frame_age_s"],
        }

    def submit(
        self,
        instruction: str,
        camera_source: str = "primary",
    ) -> dict[str, Any]:
        instruction = self._validate_instruction(instruction, camera_source)
        with self._condition:
            if self._closed:
                raise RuntimeError("mission service is shutting down")
            mission_id = self._active_mission_id
            update = mission_id is not None
            if mission_id is None:
                mission_id = str(uuid.uuid4())
                self._active_mission_id = mission_id
                self._mission_states[mission_id] = "accepted"
                self._events[mission_id] = deque()
                self._append_event_locked(
                    mission_id,
                    "mission.accepted",
                    {"instruction": instruction, "camera_source": camera_source},
                )
                self._prune_missions_locked()
            else:
                state = self._mission_states.get(mission_id)
                if state not in {"accepted", "running"}:
                    raise RuntimeError(f"mission cannot be updated while {state}")
                self._append_event_locked(
                    mission_id,
                    "mission.updated",
                    {"instruction": instruction, "camera_source": camera_source},
                )
            self.robot.camera_source = camera_source
        future = asyncio.run_coroutine_threadsafe(
            self.session.submit_instruction(
                mission_id,
                instruction,
                update=update,
            ),
            self._loop,
        )
        future.add_done_callback(
            lambda completed: self._submission_done(mission_id, completed)
        )
        return {
            "status": "updated" if update else "accepted",
            "mission_id": mission_id,
        }

    def has_mission(self, mission_id: str) -> bool:
        with self._condition:
            return mission_id in self._mission_states

    def wait_for_events(
        self,
        mission_id: str,
        after_sequence: int,
        timeout_s: float = 15.0,
    ) -> tuple[list[dict[str, Any]], bool]:
        with self._condition:
            if mission_id not in self._mission_states:
                raise KeyError(mission_id)

            def available() -> list[dict[str, Any]]:
                return [
                    event
                    for event in self._events[mission_id]
                    if event["seq"] > after_sequence
                ]

            events = available()
            state = self._mission_states[mission_id]
            if not events and state not in TERMINAL_STATES:
                self._condition.wait(timeout_s)
                events = available()
                state = self._mission_states[mission_id]
            return events, state in TERMINAL_STATES

    def camera(self) -> bytes | None:
        """Return the current primary view without exposing the camera host."""
        return self._camera_robot.capture_camera_frame()

    def stop(self) -> dict[str, Any]:
        reason = "Stopped from Lichtblick mission control"
        with self._condition:
            mission_id = self._active_mission_id
            if mission_id is not None:
                state = self._mission_states.get(mission_id)
                if state not in TERMINAL_STATES and state != "stopping":
                    self._mission_states[mission_id] = "stopping"
                    self._append_event_locked(
                        mission_id,
                        "mission.stopping",
                        {"reason": reason},
                    )
        coroutine = (
            self.session.abort_active(reason)
            if mission_id is not None
            else self.session.emergency_stop(reason)
        )
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        try:
            result = future.result(timeout=15.0)
        except concurrent.futures.TimeoutError:
            future.add_done_callback(
                lambda completed: self._finish_stop(mission_id, completed)
            )
            return {"status": "accepted", "reason": "stop is still in progress"}
        except Exception as error:  # noqa: BLE001 - emergency stop boundary.
            result = {"status": "failed", "reason": str(error)}
        self._record_stop_result(mission_id, result)
        return result

    def _finish_stop(
        self,
        mission_id: str | None,
        future: concurrent.futures.Future[Any],
    ) -> None:
        try:
            result = future.result()
        except Exception as error:  # noqa: BLE001 - emergency stop boundary.
            result = {"status": "failed", "reason": str(error)}
        self._record_stop_result(mission_id, result)

    def _record_stop_result(
        self,
        mission_id: str | None,
        result: dict[str, Any],
    ) -> None:
        if mission_id is None:
            return
        with self._condition:
            if self._mission_states.get(mission_id) not in TERMINAL_STATES:
                self._mission_states[mission_id] = "stopped"
                self._active_mission_id = None
                self._append_event_locked(
                    mission_id,
                    "mission.stopped",
                    {"stop_result": result},
                )

    def _direct_action(self, name: str) -> dict[str, Any]:
        with self._condition:
            if self._active_mission_id is not None:
                raise RuntimeError("stop the active mission before a direct action")
        return self.guard.execute(name, {})

    def dock(self) -> dict[str, Any]:
        return self._direct_action("dock")

    def undock(self) -> dict[str, Any]:
        return self._direct_action("undock")

    def close(self) -> None:
        with self._condition:
            if self._closed:
                return
            active = self._active_mission_id is not None
        if active:
            self.stop()
        with self._condition:
            self._closed = True
        try:
            future = asyncio.run_coroutine_threadsafe(self.session.shutdown(), self._loop)
            future.result(timeout=15.0)
        except Exception as error:  # noqa: BLE001 - shutdown must continue.
            print(f"WARN mission session shutdown failed: {error}", flush=True)
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._loop_thread.join(timeout=5.0)


def _sse_bytes(event: dict[str, Any]) -> bytes:
    data = json.dumps(event, separators=(",", ":"))
    return (
        f"id: {event['seq']}\n"
        f"event: {event['type']}\n"
        f"data: {data}\n\n"
    ).encode("utf-8")


def make_handler(service: MissionService):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

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

        def _event_stream(self, mission_id: str) -> None:
            if not service.has_mission(mission_id):
                self._json_response(HTTPStatus.NOT_FOUND, {"status": "not_found"})
                return
            try:
                after_sequence = int(self.headers.get("Last-Event-ID", "0"))
            except ValueError:
                after_sequence = 0
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            try:
                while True:
                    events, terminal = service.wait_for_events(
                        mission_id,
                        after_sequence,
                    )
                    if events:
                        for event in events:
                            self.wfile.write(_sse_bytes(event))
                            after_sequence = event["seq"]
                        self.wfile.flush()
                    elif not terminal:
                        self.wfile.write(b": keepalive\n\n")
                        self.wfile.flush()
                    if terminal:
                        self.close_connection = True
                        return
            except (BrokenPipeError, ConnectionResetError):
                return

        def _camera_stream(self) -> None:
            camera_url = getattr(service, "camera_url", None)
            if camera_url:
                upstream_request = urllib_request.Request(
                    camera_url.rstrip("/") + "/stream",
                    headers={"Accept": "multipart/x-mixed-replace"},
                )
                try:
                    upstream = urllib_request.urlopen(upstream_request, timeout=30)
                except (OSError, TimeoutError):
                    upstream = None
                if upstream is not None:
                    self.send_response(HTTPStatus.OK)
                    self.send_header(
                        "Content-Type",
                        upstream.headers.get(
                            "Content-Type",
                            "multipart/x-mixed-replace; boundary=frame",
                        ),
                    )
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Connection", "close")
                    self.send_header("X-Accel-Buffering", "no")
                    self.end_headers()
                    try:
                        with upstream:
                            while chunk := upstream.read1(64 * 1024):
                                self.wfile.write(chunk)
                                self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        pass
                    self.close_connection = True
                    return

            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            try:
                while True:
                    started = time.monotonic()
                    frame = service.camera()
                    if frame:
                        part = (
                            b"--frame\r\n"
                            b"Content-Type: image/jpeg\r\n"
                            + f"Content-Length: {len(frame)}\r\n\r\n".encode("ascii")
                            + frame
                            + b"\r\n"
                        )
                        self.wfile.write(part)
                        self.wfile.flush()
                    elapsed = time.monotonic() - started
                    time.sleep(max(0.0, service.browser_camera_interval_s - elapsed))
            except (BrokenPipeError, ConnectionResetError):
                self.close_connection = True
                return

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path == "/v1/camera/stream":
                self._camera_stream()
                return
            if path == "/v1/camera":
                frame = service.camera()
                if frame is None:
                    self._json_response(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        {"status": "failed", "reason": "no fresh camera frame"},
                    )
                else:
                    self._jpeg_response(HTTPStatus.OK, frame)
                return
            if path.startswith("/v1/events/"):
                mission_id = path.removeprefix("/v1/events/")
                self._event_stream(mission_id)
                return
            if path != "/v1/health":
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
                    payload = service.submit(
                        str(body.get("instruction", "")),
                        str(body.get("camera_source", "primary")),
                    )
                    self._json_response(HTTPStatus.ACCEPTED, payload)
                    return
                if self.path == "/v1/stop":
                    self._request_json()
                    self._json_response(HTTPStatus.OK, service.stop())
                    return
                if self.path == "/v1/dock":
                    self._request_json()
                    self._json_response(HTTPStatus.OK, service.dock())
                    return
                if self.path == "/v1/undock":
                    self._request_json()
                    self._json_response(HTTPStatus.OK, service.undock())
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
    tts_url = os.environ.get("SILLY_TTS_URL")
    camera_interval_s = float(os.environ.get("SILLY_CAMERA_INTERVAL_S", "1.0"))
    heartbeat_idle_s = float(os.environ.get("SILLY_HEARTBEAT_IDLE_S", "1.0"))
    browser_camera_fps = float(
        os.environ.get("SILLY_BROWSER_CAMERA_FPS", str(DEFAULT_BROWSER_CAMERA_FPS))
    )
    service = MissionService(
        api_key=api_key,
        robot_url=robot_url,
        camera_url=camera_url,
        tts_url=tts_url,
        camera_interval_s=camera_interval_s,
        heartbeat_idle_s=heartbeat_idle_s,
        browser_camera_fps=browser_camera_fps,
    )
    server = ThreadingHTTPServer((host, port), make_handler(service))
    print(f"Mission API: http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        service.close()
    return 0
