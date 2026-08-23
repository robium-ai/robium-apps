from __future__ import annotations

import multiprocessing as mp
import os
import threading
import time
from contextlib import asynccontextmanager

import gradio as gr
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from act_aloha_cube_transfer import config
from act_aloha_cube_transfer.demo.episode_runner import EpisodeRunner
from act_aloha_cube_transfer.demo.theme import CSS, THEME
from act_aloha_cube_transfer.demo.ui import build_ui


def create_gateway() -> FastAPI:
    runner = EpisodeRunner(device=os.environ.get("POLICY_DEVICE") or "cpu")
    state = {
        "session": None,
        "claimed_at": None,
        "ready": False,
        "start": time.time(),
        "log": ["gateway up — checking baked ACT checkpoint and ALOHA renderer…"],
    }

    def boot() -> None:
        try:
            seed = int(runner.evidence["local"]["selected_seed"])
            inference_s = runner.healthcheck(seed)
            state["ready"] = True
            state["log"].append(
                f"ready — {runner.device} inference {inference_s * 1000:.0f} ms, official ACT checkpoint"
            )
            print("DEMO READY", flush=True)
        except Exception as exc:
            state["log"].append(f"BOOT FAILED: {exc}")
            print(f"BOOT FAILED: {exc}", flush=True)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        threading.Thread(target=boot, name="policy-boot", daemon=True).start()
        yield

    gateway = FastAPI(lifespan=lifespan)
    gateway.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^https://(www\.)?robium\.(ai|org)$|^http://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @gateway.post("/start")
    def start(session: str | None = None):
        if session != state["session"]:
            state["claimed_at"] = time.time()
        state["session"] = session or "anonymous"
        state["claimed_at"] = state["claimed_at"] or time.time()
        return {"ok": True}

    @gateway.get("/status")
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

    @gateway.post("/shutdown")
    def shutdown(session: str | None = None):
        if state["session"] is None or session != state["session"]:
            return JSONResponse({"error": "forbidden"}, status_code=403)
        runner.cancel()
        threading.Timer(0.2, os._exit, args=(0,)).start()
        return {"bye": True}

    @gateway.get("/ui-status")
    def ui_status():
        return {"ready": state["ready"], "message": state["log"][-1]}

    @gateway.get("/")
    def root():
        return {"service": "robium demo gateway (act-aloha-cube-transfer)"}

    return gr.mount_gradio_app(
        gateway,
        build_ui(runner),
        path="/ui",
        theme=THEME,
        css=CSS,
        footer_links=[],
    )


# Spawned rollout workers import this module as __mp_main__. They must not
# recursively construct the Gradio app or launch another preview subprocess.
app = create_gateway() if mp.current_process().name == "MainProcess" else FastAPI()


def main() -> None:
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8765")), log_level="info")


if __name__ == "__main__":
    main()
