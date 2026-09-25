"""FastAPI integration boundary for MuJoCo, speech, tracking, and ER2."""

from __future__ import annotations

import asyncio
import contextlib
import math
import os
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .brain import Er2Brain
from .config import MAX_AUDIO_SECONDS, MAX_SPEECH_CHARS, SIM_SOURCE
from .router import Command, route
from .speech import LocalSpeech
from .tracking import face_to_pose


def _load_simulator() -> tuple[Any, Any, Any, Any]:
    source = SIM_SOURCE / "src"
    if not source.is_dir():
        raise RuntimeError("stackchan-simulator is missing; run ./app build")
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))
    from stackchan_sim.web import contract
    from stackchan_sim.web.server import ConnectionManager, _dispatch
    from stackchan_sim.web.simloop import SimLoop

    return contract, ConnectionManager, SimLoop, _dispatch


class CommandRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_SPEECH_CHARS)


class TrackRequest(BaseModel):
    x: float
    y: float
    confidence: float = 1.0


class SimulationController:
    def __init__(self, sim: Any):
        self.sim = sim
        self.tracking = False
        self._animation_lock = asyncio.Lock()

    def move(self, yaw: float, pitch: float) -> None:
        yaw = max(-40.0, min(40.0, float(yaw)))
        pitch = max(10.0, min(80.0, float(pitch)))
        self.sim.set_mode("manual")
        self.sim.set_target(math.radians(yaw), math.radians(pitch))

    async def animate(self, name: str) -> None:
        poses = {
            "nod": [(0, 25), (0, 68), (0, 45)],
            "shake": [(-32, 45), (32, 45), (0, 45)],
            "showcase": [(30, 60), (-30, 30), (0, 45)],
        }
        if name not in poses:
            raise ValueError(f"unknown animation: {name}")
        async with self._animation_lock:
            for yaw, pitch in poses[name]:
                self.move(yaw, pitch)
                await asyncio.sleep(0.28)

    async def apply(self, command: Command) -> dict[str, Any]:
        if command.action == "move":
            self.move(command.yaw, command.pitch)
        elif command.action == "center":
            self.move(0, 45)
        elif command.action in {"nod", "shake", "showcase"}:
            await self.animate(command.action)
        self.sim.speak(command.speech)
        if command.tracking == "start":
            self.tracking = True
        elif command.tracking == "stop":
            self.tracking = False
        return {
            "status": "succeeded",
            "action": command.action,
            "speech": command.speech,
            "tracking": command.tracking,
        }

    async def er2_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "move_head":
            self.move(arguments.get("yaw", 0), arguments.get("pitch", 45))
        elif name == "animate":
            await self.animate(str(arguments.get("animation", "")))
        elif name == "track_face":
            self.tracking = bool(arguments.get("enabled"))
            if not self.tracking:
                self.move(0, 45)
        elif name == "speak":
            message = str(arguments.get("message", "")).strip()[:MAX_SPEECH_CHARS]
            if not message:
                raise ValueError("speech message is empty")
            self.sim.speak(message)
        else:
            raise ValueError(f"tool is not allowed: {name}")
        return {"status": "succeeded", "tracking": self.tracking}


def create_app(*, brain_mode: str = "local") -> FastAPI:
    contract, ConnectionManager, SimLoop, dispatch = _load_simulator()
    manager = ConnectionManager()
    sim = SimLoop(manager.broadcast)
    controller = SimulationController(sim)
    speech = LocalSpeech()
    er2 = Er2Brain(os.environ.get("GEMINI_API_KEY", "")) if brain_mode == "er2" else None
    task: asyncio.Task[Any] | None = None

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        nonlocal task
        task = asyncio.create_task(sim.run())
        try:
            yield
        finally:
            sim.stop()
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(title="Stack-chan ER2 Simulator", lifespan=lifespan)
    app.state.sim = sim
    app.state.controller = controller
    app.state.speech = speech

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {"ok": True, "brain": brain_mode, **speech.status()}

    @app.get("/api/status")
    async def status() -> dict[str, Any]:
        return {
            "brain": brain_mode,
            "tracking": controller.tracking,
            "speech": speech.status(),
            "privacy": "Camera frames stay in the browser; only normalized face coordinates arrive here.",
        }

    @app.post("/api/command")
    async def command(request: CommandRequest) -> dict[str, Any]:
        if er2 is None:
            return await controller.apply(route(request.text))
        response = await er2.respond(request.text, controller.er2_tool)
        if response:
            sim.speak(response)
        return {
            "status": "succeeded",
            "action": "er2",
            "speech": response,
            "tracking": "start" if controller.tracking else None,
        }

    @app.post("/api/transcribe")
    async def transcribe(request: Request, sample_rate: int) -> dict[str, str]:
        body = await request.body()
        maximum = MAX_AUDIO_SECONDS * sample_rate * 4
        if len(body) > maximum:
            return JSONResponse({"error": "audio is longer than 12 seconds"}, status_code=413)
        text = await asyncio.to_thread(speech.transcribe, body, sample_rate)
        return {"text": text}

    @app.post("/api/tts")
    async def tts(request: SpeechRequest) -> Response:
        wav = await asyncio.to_thread(speech.synthesize, request.text)
        return Response(wav, media_type="audio/wav", headers={"Cache-Control": "no-store"})

    @app.post("/api/track")
    async def track(request: TrackRequest) -> dict[str, Any]:
        if request.confidence < 0.4:
            return {"status": "ignored", "reason": "low confidence"}
        controller.tracking = True
        yaw, pitch = face_to_pose(request.x, request.y)
        controller.move(yaw, pitch)
        return {"status": "succeeded", "yaw": yaw, "pitch": pitch}

    @app.post("/api/track/stop")
    async def stop_tracking() -> dict[str, str]:
        controller.tracking = False
        controller.move(0, 45)
        return {"status": "succeeded"}

    @app.get("/api/model")
    async def api_model() -> JSONResponse:
        return JSONResponse(contract.model_metadata())

    mesh_dir = SIM_SOURCE / "models" / "stackchan" / "meshes"

    @app.get("/meshes/{name}")
    async def meshes(name: str) -> Response:
        if name != Path(name).name or not name.lower().endswith(".stl"):
            return PlainTextResponse("not found", status_code=404)
        path = (mesh_dir / name).resolve()
        if path.parent != mesh_dir.resolve() or not path.is_file():
            return PlainTextResponse("not found", status_code=404)
        return Response(path.read_bytes(), media_type="model/stl")

    @app.get("/api/recording.csv")
    async def recording_csv() -> Response:
        return Response(sim.recording_csv(), media_type="text/csv")

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await manager.connect(ws)
        try:
            await ws.send_json(sim.state_message())
            while True:
                message = await ws.receive_json()
                try:
                    changed = dispatch(sim, message)
                except Exception as error:  # noqa: BLE001 - WebSocket protocol boundary.
                    await ws.send_json({"type": contract.MSG_ERROR, "message": str(error)})
                    continue
                if changed:
                    await manager.broadcast(sim.state_message())
        except WebSocketDisconnect:
            pass
        finally:
            manager.disconnect(ws)

    sim_static = SIM_SOURCE / "src" / "stackchan_sim" / "web" / "static"
    app.mount("/sim", StaticFiles(directory=str(sim_static), html=True), name="simulator")
    local_static = Path(__file__).resolve().parent / "static"
    app.mount("/", StaticFiles(directory=str(local_static), html=True), name="demo")
    return app
