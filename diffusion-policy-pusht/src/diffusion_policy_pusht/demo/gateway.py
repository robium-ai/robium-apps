"""Session gateway for the hosted PushT demo, with Gradio mounted at ``/ui``."""

from __future__ import annotations

import json
import os
import threading
import time
from contextlib import asynccontextmanager

import gradio as gr
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from diffusion_policy_pusht import config
from diffusion_policy_pusht.demo.episode_runner import EpisodeRunner
from diffusion_policy_pusht.demo.ui import CSS, THEME, build_ui


class RunnerHandle:
    """Expose lightweight preview/UI metadata while the real policy boots."""

    def __init__(self) -> None:
        self.manifest = json.loads(config.DEMO_LADDER_MANIFEST.read_text())
        self.models = {model["name"]: model for model in self.manifest["models"]}
        self.default_model = self.manifest["selected_model"]
        self.default_inference_mode = self.manifest["default_inference_mode"]
        self.device = config.demo_device()
        self._runner: EpisodeRunner | None = None

    def bind(self, runner: EpisodeRunner) -> None:
        self._runner = runner
        self.device = runner.device

    @property
    def busy(self) -> bool:
        return self._runner is not None and self._runner.busy

    def preview(self, shape: str, seed: int):
        return EpisodeRunner.preview(shape, seed)

    def cancel(self) -> None:
        if self._runner is not None:
            self._runner.cancel()

    def run(self, *args, **kwargs):
        if self._runner is None:
            raise RuntimeError("the policy is still loading; wait for Ready and try again")
        yield from self._runner.run(*args, **kwargs)


handle = RunnerHandle()
state = {
    "session": None,
    "claimed_at": None,
    "ready": False,
    "start": time.time(),
    "log": ["gateway up — loading official checkpoint + PushT environment…"],
}


def _boot() -> None:
    try:
        state["log"].append(f"loading official 175k policy on {handle.device}…")
        runner = EpisodeRunner(device=handle.device)
        handle.bind(runner)
        state["ready"] = True
        state["log"].append(f"ready — {runner.device} inference, official 175k policy")
        print("DEMO READY", flush=True)
    except Exception as exc:
        state["log"].append(f"BOOT FAILED: {exc}")
        print(f"BOOT FAILED: {exc}", flush=True)


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    threading.Thread(target=_boot, name="policy-boot", daemon=True).start()
    yield


app = FastAPI(lifespan=_lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https://(www\.)?robium\.(ai|org)$|^http://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/start")
def start(session: str | None = None):
    if handle.busy and session != state["session"]:
        handle.cancel()
    if session != state["session"]:
        state["claimed_at"] = time.time()
    state["session"] = session or "anonymous"
    state["claimed_at"] = state["claimed_at"] or time.time()
    return {"ok": True}


@app.get("/status")
def status(session: str | None = None):
    if state["session"] and session != state["session"]:
        return JSONResponse({"error": "not your instance"}, status_code=409)
    elapsed = int(time.time() - (state["claimed_at"] or state["start"]))
    return {
        "claimed": state["session"] is not None,
        "ready": state["ready"],
        "rtf": None,
        "nodes": 0,
        "uptime_s": elapsed,
        "remaining_s": max(0, config.DEMO_SESSION_SECONDS - elapsed),
        "fleet": {"running": None, "budget": config.DEMO_FLEET_BUDGET},
        "log": state["log"],
    }


@app.post("/shutdown")
def shutdown(session: str | None = None):
    if state["session"] is None or session != state["session"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)
    handle.cancel()
    threading.Timer(0.2, os._exit, args=(0,)).start()
    return {"bye": True}


@app.get("/ui-status")
def ui_status():
    return {
        "ready": state["ready"],
        "message": state["log"][-1] if state["log"] else "Starting…",
    }


@app.get("/")
def root():
    return {"service": "robium demo gateway (diffusion-policy-pusht)"}


app = gr.mount_gradio_app(
    app,
    build_ui(handle),
    path="/ui",
    theme=THEME,
    css=CSS,
    footer_links=[],
)


def main() -> None:
    uvicorn.run(app, host="0.0.0.0", port=config.DEMO_PORT, log_level="info")


if __name__ == "__main__":
    main()
