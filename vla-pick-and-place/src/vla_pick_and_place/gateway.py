"""Capability-scoped FastAPI and Gradio gateway."""

from __future__ import annotations

import os
import re
import threading
import time
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

import gradio as gr
import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel

from vla_pick_and_place.rollout import (
    DeterministicFakePolicy,
    FixtureEnvironment,
    RolloutBusyError,
    RolloutRunner,
)
from vla_pick_and_place.ui import build_ui

CAPABILITY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,128}$")


class RolloutRequest(BaseModel):
    state_id: int
    prompt: str


def create_gateway(
    *,
    capability: str,
    runner: RolloutRunner,
    terminate: Callable[[], None],
    ready_seconds: int = 600,
    clock: Callable[[], float] = time.monotonic,
) -> FastAPI:
    if not CAPABILITY_PATTERN.fullmatch(capability):
        raise ValueError("capability must be 32-128 URL-safe characters")
    if ready_seconds <= 0:
        raise ValueError("ready_seconds must be positive")
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    prefix = f"/c/{capability}"
    state = {
        "claimed": False,
        "phase": "ready",
        "selected_state_id": None,
        "outcome": None,
    }
    ready_started = clock()

    def remaining_seconds() -> int:
        return max(0, int(ready_seconds - (clock() - ready_started)))

    def expired() -> bool:
        return clock() - ready_started >= ready_seconds

    @app.post(f"{prefix}/claim")
    def claim():
        state["claimed"] = True
        return {"claimed": True, "phase": state["phase"]}

    @app.get(f"{prefix}/status")
    def status():
        return {
            "claimed": state["claimed"],
            "phase": (
                "expired" if expired() else "running" if runner.busy else state["phase"]
            ),
            "remaining_s": remaining_seconds(),
            "selected_state_id": state["selected_state_id"],
            "outcome": state["outcome"],
        }

    @app.get(f"{prefix}/stream/status")
    def stream_status():
        return status()

    @app.post(f"{prefix}/rollout")
    def rollout(request: RolloutRequest):
        if expired():
            raise HTTPException(status_code=410, detail="session expired")
        frames = []
        state["selected_state_id"] = request.state_id
        state["phase"] = "running"
        try:
            result = runner.run(
                request.state_id,
                request.prompt,
                lambda event: (
                    frames.append(event.frame) if event.frame is not None else None
                ),
            )
        except RolloutBusyError as error:
            raise HTTPException(status_code=409, detail="busy") from error
        finally:
            state["phase"] = "ready"
        state["outcome"] = result.success
        response = asdict(result)
        response.pop("prompt", None)
        response.pop("action_latency_ms", None)
        response["frame_count"] = len(frames)
        return response

    @app.post(f"{prefix}/cancel")
    def cancel():
        runner.cancel()
        return {"cancelling": True}

    @app.post(f"{prefix}/shutdown")
    def shutdown(background_tasks: BackgroundTasks):
        state["phase"] = "stopping"
        background_tasks.add_task(terminate)
        return {"deleting": True}

    return gr.mount_gradio_app(
        app,
        build_ui(runner),
        path=f"{prefix}/ui",
        root_path=f"{prefix}/ui",
        show_error=True,
    )


def _default_runner() -> RolloutRunner:
    mode = os.environ.get("VLA_RUNTIME_MODE", "fake")
    if mode == "fake":
        fixture_dir = Path(__file__).parents[2] / "test-assets" / "fixtures"
        return RolloutRunner(FixtureEnvironment(fixture_dir), DeterministicFakePolicy())
    if mode == "real":
        from vla_pick_and_place.real import build_real_runner

        execution_profile = os.environ.get("VLA_POLICY_EXECUTION", "eager")
        return build_real_runner(execution_profile=execution_profile)
    raise RuntimeError("VLA_RUNTIME_MODE must be fake or real")


def main() -> None:
    capability = os.environ.get("VLA_CAPABILITY", "")
    port = int(os.environ.get("VLA_GATEWAY_PORT", "8765"))
    ready_seconds = int(os.environ.get("VLA_READY_SECONDS", "600"))

    def terminate() -> None:
        os._exit(0)

    app = create_gateway(
        capability=capability,
        runner=_default_runner(),
        terminate=terminate,
        ready_seconds=ready_seconds,
    )
    print("DEMO READY", flush=True)
    timer = threading.Timer(ready_seconds, terminate)
    timer.daemon = True
    timer.start()
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
