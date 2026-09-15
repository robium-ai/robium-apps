"""Gemini Robotics ER 2 Streaming clients connected to a guarded adapter."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

from .config import MODEL, SYSTEM_INSTRUCTION
from .guard import GuardRejected, MissionGuard
from .tools import live_tools

PCM_CHUNK_BYTES = 3200  # 100 ms of signed 16-bit mono PCM at 16 kHz.
MAX_PROCESSED_CALLS = 256
INITIAL_CAMERA_TIMEOUT_S = 0.5

STATEFUL_TERMINAL_TOOLS = frozenset(
    {
        "move_distance",
        "rotate_by",
        "move_for_duration",
        "navigate_to_location",
        "move_forward",
        "look_around",
        "approach_object",
        "face_nearest_person",
        "dock",
        "undock",
        "stop",
    }
)

CAMERA_GEOMETRY_FIELDS = (
    "width",
    "height",
    "horizontal_fov_deg",
    "vertical_fov_deg",
    "mount_yaw_deg",
    "mount_pitch_deg",
)

ODOMETRY_FIELDS = (
    "frame_id",
    "x",
    "y",
    "yaw_rad",
    "linear_mps",
    "angular_rad_s",
)

SessionEventCallback = Callable[[str, str, dict[str, Any]], None]


def iter_pcm_chunks(data: bytes, chunk_bytes: int = PCM_CHUNK_BYTES) -> Iterable[bytes]:
    if chunk_bytes <= 0 or chunk_bytes % 2:
        raise ValueError("PCM chunk size must be a positive, even byte count")
    if len(data) % 2:
        raise ValueError("16-bit PCM input must contain an even number of bytes")
    for offset in range(0, len(data), chunk_bytes):
        yield data[offset : offset + chunk_bytes]


def _selected_fields(value: Any, fields: Iterable[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {field: value[field] for field in fields if value.get(field) is not None}


def _camera_geometry(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cameras = state.get("cameras")
    if not isinstance(cameras, dict):
        return {}
    geometry: dict[str, dict[str, Any]] = {}
    for name, camera in cameras.items():
        if not isinstance(camera, dict):
            continue
        if (
            str(name) != "primary"
            and not camera.get("topic")
            and camera.get("fresh") is not True
        ):
            continue
        selected = _selected_fields(camera, CAMERA_GEOMETRY_FIELDS)
        if selected:
            geometry[str(name)] = selected
    return geometry


def _motion_summary(state: dict[str, Any]) -> dict[str, Any]:
    motion = state.get("motion")
    summary = _selected_fields(motion, ("state", "action", "elapsed_s"))
    odometry = state.get("odometry")
    if isinstance(odometry, dict):
        for field in ("linear_mps", "angular_rad_s"):
            value = odometry.get(field)
            if value is not None:
                summary[field] = value
    return summary


def _state_alerts(state: dict[str, Any]) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    status = state.get("status")
    if status not in {None, "ok", "succeeded"}:
        alerts.append(
            {
                "kind": "robot_status",
                "status": status,
                **({"reason": state["reason"]} if state.get("reason") else {}),
            }
        )
    cameras = state.get("cameras")
    if isinstance(cameras, dict):
        for name, camera in cameras.items():
            if not isinstance(camera, dict):
                continue
            if (
                str(name) != "primary"
                and not camera.get("topic")
                and camera.get("fresh") is not True
            ):
                continue
            error = camera.get("error")
            if camera.get("fresh") is False or error:
                alerts.append(
                    {
                        "kind": "camera",
                        "camera": str(name),
                        "fresh": camera.get("fresh") is True,
                        **(
                            {"age_s": camera["age_s"]}
                            if camera.get("age_s") is not None
                            else {}
                        ),
                        **({"error": error} if error else {}),
                    }
                )
    return alerts


def compact_heartbeat_state(
    state: dict[str, Any], active_tool: dict[str, Any] | None
) -> dict[str, Any]:
    tool = None
    if active_tool:
        tool = {
            "name": active_tool.get("name"),
            "state": "running",
            "elapsed_s": active_tool.get("elapsed_s"),
        }
    summary: dict[str, Any] = {
        "task": "active",
        "tool": tool,
        "motion": _motion_summary(state),
    }
    if isinstance(state.get("is_docked"), bool):
        summary["is_docked"] = state["is_docked"]
    alerts = _state_alerts(state)
    if alerts:
        summary["alerts"] = alerts
    return summary


def compact_robot_state(
    state: dict[str, Any], *, include_camera_geometry: bool = False
) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    if state.get("status") is not None:
        summary["status"] = state["status"]
    if state.get("reason"):
        summary["reason"] = state["reason"]
    if isinstance(state.get("is_docked"), bool):
        summary["is_docked"] = state["is_docked"]
    motion = _motion_summary(state)
    if motion:
        summary["motion"] = motion
    odometry = _selected_fields(state.get("odometry"), ODOMETRY_FIELDS)
    if odometry:
        summary["odometry"] = odometry
    locations = state.get("locations")
    if isinstance(locations, list) and locations:
        summary["locations"] = locations
    if include_camera_geometry:
        geometry = _camera_geometry(state)
        if geometry:
            summary["camera_geometry"] = geometry
    alerts = _state_alerts(state)
    if alerts:
        summary["alerts"] = alerts
    return summary


def _live_config() -> types.LiveConnectConfig:
    return types.LiveConnectConfig(
        response_modalities=["TEXT"],
        tools=live_tools(),
        system_instruction=types.Content(
            parts=[types.Part(text=SYSTEM_INSTRUCTION)]
        ),
        # Video sessions otherwise have a short context lifetime. The WebSocket
        # can still be rotated by the server, which the persistent client handles.
        context_window_compression=types.ContextWindowCompressionConfig(
            sliding_window=types.SlidingWindow()
        ),
    )


class GeminiRoboticsLiveAgent:
    """Compatibility client for the single-turn CLI diagnostic."""

    def __init__(self, api_key: str, guard: MissionGuard, model: str = MODEL):
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required for live mode")
        self.client = genai.Client(api_key=api_key)
        self.guard = guard
        self.model = model

    def _config(self) -> types.LiveConnectConfig:
        return _live_config()

    async def _send_input(
        self,
        session: Any,
        text: str | None,
        image_path: Path | None,
        audio_path: Path | None,
        image_bytes: bytes | None = None,
    ) -> None:
        if audio_path is not None and text:
            raise ValueError("send either --text or --audio in one live turn, not both")

        if image_path is not None and image_bytes is not None:
            raise ValueError("send a file image or robot-camera image, not both")

        image = image_bytes
        if image_path is not None:
            if image_path.suffix.lower() not in {".jpg", ".jpeg"}:
                raise ValueError("image input must be a JPEG file")
            image = image_path.read_bytes()

        if image is not None and audio_path is not None:
            await session.send_realtime_input(
                video=types.Blob(data=image, mime_type="image/jpeg")
            )
        elif image is not None:
            parts = [
                types.Part(inline_data=types.Blob(data=image, mime_type="image/jpeg"))
            ]
            if text:
                parts.append(types.Part(text=text))
            await session.send_client_content(
                turns=types.Content(role="user", parts=parts),
                turn_complete=True,
            )
        elif text:
            await session.send_client_content(
                turns=types.Content(role="user", parts=[types.Part(text=text)]),
                turn_complete=True,
            )

        if audio_path is not None:
            for chunk in iter_pcm_chunks(audio_path.read_bytes()):
                await session.send_realtime_input(
                    media=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
                )
            await session.send_realtime_input(audio_stream_end=True)

    async def _receive_turn(self, session: Any, timeout_s: float) -> list[str]:
        text_parts: list[str] = []

        async def receive() -> None:
            async for message in session.receive():
                if message.server_content:
                    content = message.server_content
                    if content.model_turn and content.model_turn.parts:
                        for part in content.model_turn.parts:
                            if part.text:
                                text_parts.append(part.text)
                                print(part.text, end="", flush=True)
                    if content.turn_complete:
                        print()
                        return
                if message.tool_call:
                    responses = []
                    for call in message.tool_call.function_calls:
                        try:
                            result = await asyncio.to_thread(
                                self.guard.execute,
                                call.name,
                                dict(call.args or {}),
                            )
                        except GuardRejected as error:
                            result = {"status": "rejected", "reason": str(error)}
                        print(
                            f"\n[tool] {call.name}({dict(call.args or {})}) -> {result}"
                        )
                        responses.append(
                            types.FunctionResponse(
                                name=call.name,
                                response=result,
                                id=call.id,
                            )
                        )
                        take_frames = getattr(
                            self.guard.adapter, "consume_camera_frames", None
                        )
                        if take_frames is not None:
                            for frame in take_frames():
                                await session.send_realtime_input(
                                    video=types.Blob(
                                        data=frame,
                                        mime_type="image/jpeg",
                                    )
                                )
                    await session.send_tool_response(function_responses=responses)

        try:
            await asyncio.wait_for(receive(), timeout=timeout_s)
        except TimeoutError:
            try:
                await asyncio.to_thread(
                    self.guard.execute,
                    "stop",
                    {"reason": "Gemini turn timed out"},
                )
            except Exception as error:  # noqa: BLE001 - emergency cancellation.
                print(f"WARN failed to cancel robot after timeout: {error}")
            raise
        return text_parts

    async def run_once(
        self,
        *,
        text: str | None = None,
        image_path: Path | None = None,
        audio_path: Path | None = None,
        image_bytes: bytes | None = None,
        timeout_s: float = 240.0,
    ) -> list[str]:
        if not any((text, image_path, audio_path, image_bytes)):
            raise ValueError("live mode needs --text, --image, or --audio")
        async with self.client.aio.live.connect(
            model=self.model,
            config=self._config(),
        ) as session:
            await self._send_input(
                session,
                text,
                image_path,
                audio_path,
                image_bytes,
            )
            return await self._receive_turn(session, timeout_s)


@dataclass(order=True)
class _QueuedWrite:
    priority: int
    sequence: int
    kind: str = field(compare=False)
    mission_id: str = field(compare=False)
    payload: Any = field(compare=False)


class _ReconnectRequested(ConnectionError):
    pass


class _TurnTimedOut(TimeoutError):
    pass


class PersistentGeminiSession:
    """One serialized Gemini Live connection for the robot control process."""

    def __init__(
        self,
        api_key: str,
        guard: MissionGuard,
        event_callback: SessionEventCallback,
        *,
        model: str = MODEL,
        client: Any | None = None,
        camera_interval_s: float = 1.0,
        heartbeat_idle_s: float = 1.0,
        turn_timeout_s: float = 240.0,
        max_reconnect_attempts: int = 5,
    ):
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required by the persistent session")
        if camera_interval_s < 0:
            raise ValueError("camera interval must not be negative")
        if 0 < camera_interval_s < 1.0:
            raise ValueError("camera interval must be at least one second")
        self.client = client or genai.Client(api_key=api_key)
        self.guard = guard
        self.event_callback = event_callback
        self.model = model
        self.camera_interval_s = camera_interval_s
        self.heartbeat_idle_s = heartbeat_idle_s
        self.turn_timeout_s = turn_timeout_s
        self.max_reconnect_attempts = max_reconnect_attempts

        self._writes: asyncio.PriorityQueue[_QueuedWrite] | None = None
        self._submit_lock: asyncio.Lock | None = None
        self._write_sequence = 0
        self._manager_task: asyncio.Task[None] | None = None
        self._camera_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._session: Any | None = None
        self._shutdown_requested = False
        self._active_mission_id: str | None = None
        self._active_instruction = ""
        self._input_revision = 0
        self._pending_turns = 0
        self._model_generating = False
        self._active_tool_count = 0
        self._active_tool_task: asyncio.Task[None] | None = None
        self._active_tool_call_id = ""
        self._active_tool_name = ""
        self._active_tool_started_at = 0.0
        self._last_tool_progress_at = 0.0
        self._turn_activity_seen = False
        self._heartbeat_pending = False
        self._last_activity = time.monotonic()
        self._last_video_send_monotonic: float | None = None
        self._last_camera_sent_at: float | None = None
        self._last_camera_status = 0.0
        self._camera_failures = 0
        self._latest_periodic_frame: tuple[str, bytes] | None = None
        self._periodic_camera_pending = False
        self._mission_tool_results: list[dict[str, Any]] = []
        self._processed_calls: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._response_call_ids: OrderedDict[str, None] = OrderedDict()

        self._status_lock = threading.Lock()
        self._connection_state = "disconnected"
        self._connection_count = 0

    def _config(self) -> types.LiveConnectConfig:
        return _live_config()

    def health_snapshot(self) -> dict[str, Any]:
        with self._status_lock:
            last_sent = self._last_camera_sent_at
            return {
                "state": self._connection_state,
                "connection_count": self._connection_count,
                "last_camera_frame_age_s": (
                    None if last_sent is None else max(0.0, time.time() - last_sent)
                ),
                "camera_send_failures": self._camera_failures,
                "active_tool": (
                    None
                    if not self._active_tool_name
                    else {
                        "call_id": self._active_tool_call_id,
                        "name": self._active_tool_name,
                        "elapsed_s": round(
                            max(0.0, time.monotonic() - self._active_tool_started_at),
                            3,
                        ),
                    }
                ),
            }

    def _set_connection_state(self, state: str) -> None:
        with self._status_lock:
            self._connection_state = state

    def _mark_camera_sent(self) -> None:
        with self._status_lock:
            self._last_camera_sent_at = time.time()

    def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        mission_id = self._active_mission_id
        if mission_id is None:
            return
        try:
            self.event_callback(mission_id, event_type, payload)
        except Exception as error:  # noqa: BLE001 - observability must not stop robot.
            print(f"WARN mission event callback failed: {error}", flush=True)

    def _ensure_queue(self) -> asyncio.PriorityQueue[_QueuedWrite]:
        if self._writes is None:
            self._writes = asyncio.PriorityQueue(maxsize=32)
        return self._writes

    async def _queue_write(
        self,
        priority: int,
        kind: str,
        mission_id: str,
        payload: Any,
    ) -> bool:
        queue = self._ensure_queue()
        self._write_sequence += 1
        item = _QueuedWrite(priority, self._write_sequence, kind, mission_id, payload)
        try:
            queue.put_nowait(item)
            return True
        except asyncio.QueueFull:
            if kind in {"camera", "heartbeat"}:
                return False
            await queue.put(item)
            return True

    def _clear_pending_writes(self) -> None:
        self._latest_periodic_frame = None
        self._periodic_camera_pending = False
        if self._writes is None:
            return
        while True:
            try:
                self._writes.get_nowait()
                self._writes.task_done()
            except asyncio.QueueEmpty:
                return

    async def submit_instruction(
        self,
        mission_id: str,
        instruction: str,
        *,
        update: bool = False,
    ) -> None:
        if self._submit_lock is None:
            self._submit_lock = asyncio.Lock()
        async with self._submit_lock:
            await self._submit_instruction_serialized(
                mission_id,
                instruction,
                update=update,
            )

    async def _submit_instruction_serialized(
        self,
        mission_id: str,
        instruction: str,
        *,
        update: bool,
    ) -> None:
        if self._shutdown_requested:
            raise RuntimeError("Gemini session is shutting down")
        if self._active_mission_id not in {None, mission_id}:
            raise RuntimeError("another mission is already active")
        new_mission = self._active_mission_id is None
        if new_mission:
            self._active_mission_id = mission_id
            self._mission_tool_results = []
            self._heartbeat_pending = False
            self._pending_turns = 0
            self._turn_activity_seen = False
        self._active_instruction = instruction
        self._input_revision += 1
        self._pending_turns += 1
        self._last_activity = time.monotonic()
        if new_mission:
            self._ensure_manager()
            initial_image = await self._capture_initial_frame()
        else:
            initial_image = None
        if self._active_mission_id != mission_id:
            return
        state = await self._robot_state_snapshot()
        await self._queue_write(
            0,
            "instruction",
            mission_id,
            {
                "text": self._instruction_with_state(
                    instruction,
                    state,
                    include_camera_geometry=new_mission,
                ),
                "revision": self._input_revision,
                "kind": "update" if update else "operator",
                "image": initial_image,
            },
        )
        if new_mission:
            self._start_mission_tasks()
        self._ensure_manager()

    async def _capture_initial_frame(self) -> bytes | None:
        capture = getattr(self.guard.adapter, "capture_camera_frame", None)
        if capture is None:
            return None
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(capture),
                timeout=INITIAL_CAMERA_TIMEOUT_S,
            )
        except Exception:  # noqa: BLE001 - a missing first frame is non-fatal.
            return None

    def _ensure_manager(self) -> None:
        if self._manager_task is None or self._manager_task.done():
            self._manager_task = asyncio.create_task(self._connection_manager())

    def _start_mission_tasks(self) -> None:
        if self.camera_interval_s > 0:
            self._camera_task = asyncio.create_task(self._camera_pump())
        if self.heartbeat_idle_s > 0:
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _connection_manager(self) -> None:
        reconnect_attempt = 0
        needs_snapshot = False
        try:
            while not self._shutdown_requested:
                mission_id = self._active_mission_id
                self._set_connection_state(
                    "reconnecting" if reconnect_attempt else "connecting"
                )
                if reconnect_attempt == 0:
                    self._emit(
                        "session.connecting",
                        {"attempt": 0, "model": self.model},
                    )
                try:
                    async with self.client.aio.live.connect(
                        model=self.model,
                        config=self._config(),
                    ) as session:
                        self._session = session
                        with self._status_lock:
                            self._connection_count += 1
                        self._set_connection_state("ready")
                        self._emit(
                            "session.ready",
                            {
                                "model": self.model,
                                "connection_count": self.health_snapshot()[
                                    "connection_count"
                                ],
                            },
                        )
                        if needs_snapshot and self._active_mission_id is not None:
                            self._pending_turns = 1
                            self._input_revision += 1
                            await self._queue_write(
                                0,
                                "instruction",
                                self._active_mission_id,
                                {
                                    "text": self._reconnect_snapshot(),
                                    "revision": self._input_revision,
                                    "kind": "resume",
                                    "image": None,
                                },
                            )
                            needs_snapshot = False
                        await self._run_connected(session)
                except asyncio.CancelledError:
                    raise
                except _TurnTimedOut as error:
                    stop_result = await self._safe_stop(str(error))
                    await self._cancel_active_tool()
                    self._emit(
                        "mission.failed",
                        {"reason": str(error), "stop_result": stop_result},
                    )
                    self._finish_active_mission()
                    return
                except Exception as error:  # noqa: BLE001 - reconnect boundary.
                    self._session = None
                    if self._active_mission_id is None:
                        self._processed_calls.clear()
                        self._set_connection_state("disconnected")
                        return
                    stop_result = await self._safe_stop(
                        "Gemini connection lost; robot stopped before reconnect"
                    )
                    await self._cancel_active_tool()
                    reconnect_attempt += 1
                    if reconnect_attempt > self.max_reconnect_attempts:
                        self._emit(
                            "mission.failed",
                            {
                                "reason": f"Gemini connection failed: {error}",
                                "stop_result": stop_result,
                            },
                        )
                        self._finish_active_mission()
                        return
                    self._clear_pending_writes()
                    self._pending_turns = 0
                    self._heartbeat_pending = False
                    self._model_generating = False
                    needs_snapshot = True
                    self._set_connection_state("reconnecting")
                    self._emit(
                        "session.reconnecting",
                        {
                            "attempt": reconnect_attempt,
                            "reason": str(error),
                            "stop_result": stop_result,
                        },
                    )
                    await asyncio.sleep(min(8.0, 2 ** (reconnect_attempt - 1)))
                finally:
                    self._session = None
                if mission_id is None and self._active_mission_id is None:
                    return
        finally:
            self._session = None
            self._set_connection_state("disconnected")

    async def _run_connected(self, session: Any) -> None:
        writer = asyncio.create_task(self._writer(session))
        receiver = asyncio.create_task(self._receiver(session))
        tasks = {writer, receiver}
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
            for task in done:
                exception = task.exception()
                if exception is not None:
                    raise exception
            raise ConnectionError("Gemini session worker exited unexpectedly")
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _writer(self, session: Any) -> None:
        queue = self._ensure_queue()
        while True:
            item = await queue.get()
            try:
                inactive_tool_response = (
                    item.kind == "tool_response"
                    and item.mission_id == ""
                    and self._active_mission_id is None
                )
                if (
                    item.mission_id != self._active_mission_id
                    and not inactive_tool_response
                ):
                    continue
                if item.kind == "instruction":
                    payload = item.payload
                    parts = []
                    if payload["image"]:
                        parts.append(
                            types.Part(
                                inline_data=types.Blob(
                                    data=payload["image"],
                                    mime_type="image/jpeg",
                                )
                            )
                        )
                    parts.append(types.Part(text=payload["text"]))
                    await session.send_client_content(
                        turns=types.Content(
                            role="user",
                            parts=parts,
                        ),
                        turn_complete=True,
                    )
                    if payload["image"]:
                        self._last_video_send_monotonic = time.monotonic()
                        self._mark_camera_sent()
                    self._last_activity = time.monotonic()
                    self._turn_activity_seen = False
                    self._emit(
                        "input.sent",
                        {
                            "kind": payload["kind"],
                            "revision": payload["revision"],
                        },
                    )
                elif item.kind == "heartbeat":
                    await session.send_realtime_input(text=item.payload["text"])
                    self._last_activity = time.monotonic()
                    self._turn_activity_seen = False
                    self._emit(
                        "input.sent",
                        {"kind": "heartbeat", "state": item.payload.get("state", {})},
                    )
                elif item.kind == "camera":
                    await self._send_camera_frame(session, item.payload)
                elif item.kind == "periodic_camera":
                    latest = self._latest_periodic_frame
                    self._latest_periodic_frame = None
                    self._periodic_camera_pending = False
                    if latest is not None and latest[0] == self._active_mission_id:
                        await self._send_camera_frame(session, latest[1])
                elif item.kind == "tool_response":
                    payload = item.payload
                    responses = (
                        payload["responses"] if isinstance(payload, dict) else payload
                    )
                    await session.send_tool_response(
                        function_responses=responses,
                    )
                    for response in responses:
                        self._emit(
                            "tool.response.sent",
                            {
                                "name": str(response.name or ""),
                                "call_id": str(response.id or ""),
                                "result": response.response,
                            },
                        )
                    if isinstance(payload, dict) and payload.get("complete"):
                        self._emit(
                            "mission.completed",
                            {
                                "summary": payload.get("summary", ""),
                                "tool_calls": len(self._mission_tool_results),
                            },
                        )
                        self._finish_active_mission()
            finally:
                queue.task_done()

    async def _send_camera_frame(self, session: Any, frame: bytes) -> None:
        if self.camera_interval_s <= 0:
            return
        if self._last_video_send_monotonic is not None:
            delay = self.camera_interval_s - (
                time.monotonic() - self._last_video_send_monotonic
            )
            if delay > 0:
                await asyncio.sleep(delay)
        await session.send_realtime_input(
            video=types.Blob(data=frame, mime_type="image/jpeg")
        )
        self._last_video_send_monotonic = time.monotonic()
        self._mark_camera_sent()

    async def _receiver(self, session: Any) -> None:
        while True:
            try:
                if self._active_mission_id is not None and self._pending_turns > 0:
                    await asyncio.wait_for(
                        self._receive_one_turn(session),
                        timeout=self.turn_timeout_s,
                    )
                else:
                    await self._receive_one_turn(session)
            except TimeoutError as error:
                raise _TurnTimedOut(
                    f"Gemini turn timed out after {self.turn_timeout_s:.0f} seconds"
                ) from error

    async def _receive_one_turn(self, session: Any) -> None:
        received = False
        async for message in session.receive():
            received = True
            if message.go_away is not None:
                raise _ReconnectRequested(
                    f"Gemini requested reconnect in {message.go_away.time_left or 'unknown time'}"
                )
            if message.server_content is not None:
                await self._handle_server_content(message.server_content)
            if message.tool_call is not None:
                await self._handle_tool_calls(session, message.tool_call.function_calls)
            if message.tool_call_cancellation is not None:
                ids = list(message.tool_call_cancellation.ids or [])
                active_tool = self.health_snapshot()["active_tool"]
                if active_tool is None or (
                    ids and active_tool["call_id"] not in ids
                ):
                    self._emit(
                        "tool.rejected",
                        {
                            "call_ids": ids,
                            "reason": "cancelled inactive tool call",
                            "ignored": True,
                        },
                    )
                    continue
                reason = (
                    f"Gemini cancelled active tool {active_tool['name']} "
                    f"({active_tool['call_id']})"
                )
                result = {"status": "cancelled", "reason": reason}
                self._emit(
                    "tool.rejected",
                    {
                        "name": active_tool["name"],
                        "call_id": active_tool["call_id"],
                        "call_ids": ids,
                        "result": result,
                    },
                )
                stop_result = await self._safe_stop(reason)
                self._emit(
                    "mission.failed",
                    {"reason": reason, "stop_result": stop_result},
                )
                self._finish_active_mission()
                return
        if not received:
            await asyncio.sleep(0.05)

    async def _handle_server_content(self, content: Any) -> None:
        if content.model_turn and content.model_turn.parts:
            for part in content.model_turn.parts:
                if part.text:
                    self._model_generating = True
                    self._turn_activity_seen = True
                    self._last_activity = time.monotonic()
                    self._emit("model.text.delta", {"text": part.text})
        if content.turn_complete:
            self._model_generating = False
            self._last_activity = time.monotonic()
            self._pending_turns = max(0, self._pending_turns - 1)
            self._heartbeat_pending = False
            self._emit(
                "model.turn.completed",
                {
                    "interrupted": bool(content.interrupted),
                    "pending_turns": self._pending_turns,
                },
            )

    async def _handle_tool_calls(self, session: Any, calls: Any) -> None:
        # A function call ends the model's generation phase even though the
        # Live turn remains blocked until the function response arrives.
        self._model_generating = False
        if self._active_mission_id is None:
            responses = [
                types.FunctionResponse(
                    name=str(call.name or ""),
                    response={"status": "rejected", "reason": "no active mission"},
                    id=str(call.id or ""),
                )
                for call in calls
            ]
            await self._queue_write(
                0, "tool_response", "", {"responses": responses, "complete": False}
            )
            return
        for call in calls:
            call_id = str(call.id or "")
            name = str(call.name or "")
            arguments = dict(call.args or {})
            self._last_activity = time.monotonic()
            self._turn_activity_seen = True
            recorded = self._processed_calls.get(call_id) if call_id else None
            if recorded is not None:
                result = recorded["result"]
                rejected = result.get("status") == "rejected"
                self._emit(
                    "tool.rejected" if rejected else "tool.finished",
                    {
                        "name": name,
                        "call_id": call_id,
                        "result": result,
                        "replayed": True,
                    },
                )
                await self._queue_tool_response(name, call_id, result)
                continue

            active = self._active_tool_task
            if active is not None and not active.done():
                reason = (
                    f"tool {name or '<unnamed>'} rejected because "
                    f"{self._active_tool_name} ({self._active_tool_call_id}) is still running"
                )
                result = {
                    "status": "rejected",
                    "reason": reason,
                    "active_call_id": self._active_tool_call_id,
                    "active_tool": self._active_tool_name,
                }
                self._emit(
                    "tool.rejected",
                    {
                        "name": name,
                        "call_id": call_id,
                        "arguments": arguments,
                        "result": result,
                        "conflict": True,
                    },
                )
                # A duplicate delivery of the active call must receive only the
                # original terminal response, exactly once.
                if call_id != self._active_tool_call_id:
                    await self._queue_tool_response(name, call_id, result)
                continue

            mission_id = self._active_mission_id
            self._active_tool_count = 1
            self._active_tool_call_id = call_id
            self._active_tool_name = name
            self._active_tool_started_at = time.monotonic()
            self._last_tool_progress_at = self._active_tool_started_at
            self._emit(
                "tool.started",
                {
                    "name": name,
                    "call_id": call_id,
                    "arguments": arguments,
                    "replayed": False,
                },
            )
            self._active_tool_task = asyncio.create_task(
                self._execute_tool_call(mission_id, name, call_id, arguments)
            )

    async def _execute_tool_call(
        self,
        mission_id: str,
        name: str,
        call_id: str,
        arguments: dict[str, Any],
    ) -> None:
        started = time.monotonic()
        try:
            try:
                result = await asyncio.to_thread(self.guard.execute, name, arguments)
                rejected = result.get("status") == "rejected"
            except GuardRejected as error:
                result = {"status": "rejected", "reason": str(error)}
                rejected = True
            except Exception as error:  # noqa: BLE001 - tool failure boundary.
                result = {"status": "failed", "reason": str(error)}
                rejected = False
            result = dict(result)
            result.setdefault("elapsed_s", round(time.monotonic() - started, 3))
            if name in STATEFUL_TERMINAL_TOOLS:
                terminal_state = await self._robot_state_snapshot(runtime_only=True)
                result["robot_state"] = compact_robot_state(terminal_state)
            if call_id:
                self._processed_calls[call_id] = {
                    "mission_id": mission_id,
                    "name": name,
                    "result": result,
                }
                while len(self._processed_calls) > MAX_PROCESSED_CALLS:
                    self._processed_calls.popitem(last=False)
            self._mission_tool_results.append(
                {"name": name, "call_id": call_id, "result": result}
            )
            self._last_activity = time.monotonic()
            self._emit(
                "tool.rejected" if rejected else "tool.finished",
                {
                    "name": name,
                    "call_id": call_id,
                    "result": result,
                    "replayed": False,
                },
            )
            take_frames = getattr(self.guard.adapter, "consume_camera_frames", None)
            if take_frames is not None:
                for frame in take_frames():
                    await self._queue_write(1, "camera", mission_id, frame)
            await self._queue_tool_response(
                name,
                call_id,
                result,
                complete=name == "complete_task" and result.get("status") == "succeeded",
                summary=str(result.get("summary", "")),
                mission_id=mission_id,
            )
        finally:
            if self._active_tool_call_id == call_id:
                self._active_tool_count = 0
                self._active_tool_call_id = ""
                self._active_tool_name = ""
                self._active_tool_started_at = 0.0
                self._last_tool_progress_at = 0.0
                self._active_tool_task = None

    async def _queue_tool_response(
        self,
        name: str,
        call_id: str,
        result: dict[str, Any],
        *,
        complete: bool = False,
        summary: str = "",
        mission_id: str | None = None,
    ) -> None:
        if call_id:
            if call_id in self._response_call_ids:
                return
            self._response_call_ids[call_id] = None
            while len(self._response_call_ids) > MAX_PROCESSED_CALLS:
                self._response_call_ids.popitem(last=False)
        await self._queue_write(
            0,
            "tool_response",
            mission_id if mission_id is not None else (self._active_mission_id or ""),
            {
                "responses": [
                    types.FunctionResponse(name=name, response=result, id=call_id)
                ],
                "complete": complete,
                "summary": summary,
            },
        )

    async def _camera_pump(self) -> None:
        capture = getattr(self.guard.adapter, "capture_camera_frame", None)
        if capture is None:
            return
        while self._active_mission_id is not None:
            started = time.monotonic()
            mission_id = self._active_mission_id
            frame = await asyncio.to_thread(capture)
            if mission_id != self._active_mission_id:
                return
            if frame:
                if self._connection_state == "ready":
                    await self._queue_periodic_camera(mission_id, frame)
                self._emit_camera_status(True)
            else:
                with self._status_lock:
                    self._camera_failures += 1
                self._emit_camera_status(False)
            elapsed = time.monotonic() - started
            await asyncio.sleep(max(0.0, self.camera_interval_s - elapsed))

    async def _queue_periodic_camera(self, mission_id: str, frame: bytes) -> None:
        self._latest_periodic_frame = (mission_id, frame)
        if self._periodic_camera_pending:
            return
        self._periodic_camera_pending = True
        queued = await self._queue_write(2, "periodic_camera", mission_id, None)
        if not queued:
            self._periodic_camera_pending = False

    def _emit_camera_status(self, success: bool) -> None:
        now = time.monotonic()
        if success and now - self._last_camera_status < 10.0:
            return
        if not success and now - self._last_camera_status < 5.0:
            return
        self._last_camera_status = now
        self._emit(
            "camera.status",
            {
                "status": "streaming" if success else "unavailable",
                "send_failures": self.health_snapshot()["camera_send_failures"],
            },
        )

    async def _heartbeat_loop(self) -> None:
        while self._active_mission_id is not None:
            await asyncio.sleep(min(0.5, self.heartbeat_idle_s))
            tool_running = self._active_tool_count > 0
            if (
                self._active_mission_id is None
                or self._connection_state != "ready"
                or self._model_generating
            ):
                continue
            mission_id = self._active_mission_id
            if tool_running:
                now = time.monotonic()
                if now - self._last_tool_progress_at < self.heartbeat_idle_s:
                    continue
                state = await self._robot_state_snapshot(runtime_only=True)
                active_tool = self.health_snapshot()["active_tool"]
                if active_tool is None:
                    continue
                self._last_tool_progress_at = now
                self._emit(
                    "tool.progress",
                    {
                        "name": active_tool["name"],
                        "call_id": active_tool["call_id"],
                        "elapsed_s": active_tool["elapsed_s"],
                        "state": compact_heartbeat_state(state, active_tool),
                    },
                )
                continue
            if (
                self._pending_turns > 0
                or self._heartbeat_pending
                or time.monotonic() - self._last_activity < self.heartbeat_idle_s
            ):
                continue
            state = await self._robot_state_snapshot(runtime_only=True)
            heartbeat_state = compact_heartbeat_state(state, None)
            self._heartbeat_pending = True
            self._pending_turns += 1
            guidance = (
                "No tool is active. Reassess the latest image and state, then call "
                "ack if waiting, choose one next physical action, or call "
                "complete_task if the overall instruction is achieved."
            )
            prompt = (
                "[HEARTBEAT] Task active. Inspect the latest camera image. "
                f"{guidance} Runtime state: "
                + json.dumps(heartbeat_state, separators=(",", ":"), default=str)
            )
            queued = await self._queue_write(
                3,
                "heartbeat",
                mission_id,
                {
                    "text": prompt,
                    "state": heartbeat_state,
                },
            )
            if not queued:
                self._heartbeat_pending = False
                self._pending_turns = max(0, self._pending_turns - 1)

    async def _robot_state_snapshot(
        self, *, runtime_only: bool = False
    ) -> dict[str, Any]:
        try:
            snapshot = self.guard.adapter.health
            if runtime_only:
                snapshot = getattr(self.guard.adapter, "runtime_state", snapshot)
            state = await asyncio.to_thread(snapshot)
            return state if isinstance(state, dict) else {"status": "unavailable"}
        except Exception as error:  # noqa: BLE001 - heartbeat must keep running.
            return {"status": "unavailable", "reason": str(error)}

    @staticmethod
    def _instruction_with_state(
        instruction: str,
        state: dict[str, Any],
        *,
        include_camera_geometry: bool,
    ) -> str:
        context = compact_robot_state(
            state,
            include_camera_geometry=include_camera_geometry,
        )
        context_label = (
            "Robot context at mission start; camera geometry is stable session "
            "context and is not repeated in heartbeats"
            if include_camera_geometry
            else "Current compact robot state for this operator update"
        )
        return (
            f"Operator instruction: {instruction}\n"
            f"{context_label}: "
            + json.dumps(context, separators=(",", ":"), default=str)
        )

    def _reconnect_snapshot(self) -> str:
        results = json.dumps(self._mission_tool_results[-8:], separators=(",", ":"))
        return (
            "Resume the active robot mission after a connection interruption. "
            f"Current operator instruction: {self._active_instruction!r}. "
            "The robot was stopped for safety when the connection failed. "
            f"Confirmed recent tool results: {results}. "
            "Do not repeat a completed physical action; continue safely from this state."
        )

    async def _safe_stop(self, reason: str) -> dict[str, Any]:
        try:
            return await asyncio.to_thread(
                self.guard.execute,
                "stop",
                {"reason": reason},
            )
        except Exception as error:  # noqa: BLE001 - emergency cancellation.
            return {"status": "failed", "reason": str(error)}

    async def _cancel_active_tool(self) -> None:
        task = self._active_tool_task
        if task is None or task is asyncio.current_task():
            return
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        self._active_tool_task = None
        self._active_tool_count = 0
        self._active_tool_call_id = ""
        self._active_tool_name = ""
        self._active_tool_started_at = 0.0
        self._last_tool_progress_at = 0.0

    def _finish_active_mission(self) -> None:
        self._active_mission_id = None
        self._active_instruction = ""
        self._pending_turns = 0
        self._model_generating = False
        self._active_tool_count = 0
        tool_task = self._active_tool_task
        if tool_task is not None and tool_task is not asyncio.current_task():
            tool_task.cancel()
        self._active_tool_task = None
        self._active_tool_call_id = ""
        self._active_tool_name = ""
        self._active_tool_started_at = 0.0
        self._last_tool_progress_at = 0.0
        self._turn_activity_seen = False
        self._heartbeat_pending = False
        self._clear_pending_writes()
        current = asyncio.current_task()
        for task in (self._camera_task, self._heartbeat_task):
            if task is not None and task is not current:
                task.cancel()
        self._camera_task = None
        self._heartbeat_task = None

    async def abort_active(self, reason: str) -> dict[str, Any]:
        self._finish_active_mission()
        manager = self._manager_task
        if manager is not None and manager is not asyncio.current_task():
            manager.cancel()
            await asyncio.gather(manager, return_exceptions=True)
        self._manager_task = None
        self._processed_calls.clear()
        self._response_call_ids.clear()
        self._set_connection_state("disconnected")
        return await self._safe_stop(reason)

    async def emergency_stop(self, reason: str) -> dict[str, Any]:
        return await self._safe_stop(reason)

    async def shutdown(self) -> None:
        self._shutdown_requested = True
        if self._active_mission_id is not None:
            await self.abort_active("Mission service is shutting down")
        manager = self._manager_task
        if manager is not None:
            manager.cancel()
            await asyncio.gather(manager, return_exceptions=True)
        self._manager_task = None
        self._set_connection_state("disconnected")
