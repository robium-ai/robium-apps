"""Demo session gateway — one process, one port (8765).

FastAPI implementing robot-navigation's session contract (so robium-website's
Controls/demoClient/orchestrator reuse unchanged) + the Gradio app mounted at
/ui. Unlike robot-navigation's gateway there is no WebSocket tunnel: the
"viewer" is the Gradio app itself, and "busy" means the simulator is executing
a command.

Contract (mirrors robot-navigation's scripts/demo_gateway.py):
  POST /start?session=U    -> claim; a foreign claim aborts an in-flight run
  GET  /status?session=U   -> robot-navigation's JSON shape; foreign -> 409
  POST /shutdown?session=U -> foreign -> 403; own -> exit the process
  /ui                      -> the Gradio app (iframed by the website)

Boot is the pinned environment coming up and passing its contract check — not
a model load. There is no checkpoint to fetch and no Hub auth to hold, so
`DEMO READY` now means "the simulator answered, and its schema is the one this
app was built against". A schema drift fails boot loudly here rather than
mislabelling frames later.
"""

import os
import threading
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from vla_pick_and_place.config import (
    DEMO_FLEET_BUDGET,
    DEMO_PORT,
    DEMO_SESSION_SECONDS,
    ENV_ID,
    NEXUS_VERSION,
)
from vla_pick_and_place.demo import dashboard
from vla_pick_and_place.demo.ui import build_ui
from vla_pick_and_place.env.nexus import set_gl_backend

state = {
    "session": None,
    "claimed_at": None,
    "ready": False,
    "worker": None,
    "start": time.time(),
    "log": ["gateway up — starting the simulator…"],
}


def _boot() -> None:
    """Heavy work in a thread so /status answers from the first second."""
    try:
        gl = set_gl_backend()
        state["log"].append(f"so101-nexus {NEXUS_VERSION} · {ENV_ID} · MUJOCO_GL={gl}")

        from vla_pick_and_place.demo.session import SimWorker
        from vla_pick_and_place.env import contract

        worker = SimWorker().start()
        # The worker owns the only env, on its own thread; the contract check
        # has to run there too or it would build a second GL context on this
        # one. `run_on_env` is that door.
        measured = worker.run_on_env(lambda env: contract.capture(env))
        problems = contract.diff(measured)
        if problems:
            raise contract.ContractError(
                "environment schema drift:\n  - " + "\n  - ".join(problems)
            )
        worker.reset(seed=0)
        state["worker"] = worker
        state["ready"] = True
        state["log"].append("ready — simulator up, contract verified")
        print("DEMO READY", flush=True)  # the orchestrator's readyLog line
    except Exception as e:  # surface boot failures in the page's log pane
        state["log"].append(f"BOOT FAILED: {e}")
        print(f"BOOT FAILED: {e}", flush=True)
        raise


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    threading.Thread(target=_boot, daemon=True).start()
    yield


app = FastAPI(lifespan=_lifespan)
app.add_middleware(
    CORSMiddleware,
    # Exact-origin reflect (ACAO:* is invalid with credentials): prod site +
    # localhost dev, same shape as robot-navigation's gateway.
    allow_origin_regex=r"^https://(www\.)?robium\.(ai|org)$|^http://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _busy() -> bool:
    return state["worker"] is not None and state["worker"].busy


@app.post("/start")
def start(session: str | None = None):
    # Claims are ALWAYS takeable here, even mid-run: a page refresh generates
    # a new session id while Gradio keeps executing the orphaned run, and
    # locally this is the only instance, so the refresh must win. Foreign
    # takeover aborts the in-flight run at its next control step. Stated
    # honestly: a second visitor can steal the instance; a cloud version needs
    # liveness-based claims instead.
    if _busy() and session != state["session"]:
        state["worker"].request_abort()
    if session != state["session"]:
        state["claimed_at"] = time.time()
    state["session"] = session or "anonymous"
    state["claimed_at"] = state["claimed_at"] or time.time()
    return {"ok": True}


@app.get("/status")
def status(session: str | None = None):
    if state["session"] and session != state["session"]:
        return JSONResponse({"error": "not your instance"}, status_code=409)
    up = int(time.time() - (state["claimed_at"] or state["start"]))
    return {
        "claimed": state["session"] is not None,
        "ready": state["ready"],
        "rtf": None,  # kept for the shared Status shape; meaningless here
        "nodes": 0,
        "uptime_s": up,
        "remaining_s": max(0, DEMO_SESSION_SECONDS - up),
        "fleet": {"running": None, "budget": DEMO_FLEET_BUDGET},
        "log": state["log"],
    }


@app.post("/shutdown")
def shutdown(session: str | None = None):
    if state["session"] is None or session != state["session"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)
    # Answer first, then exit THIS process: PID 1 in the container (AutoRemove
    # reaps it), a plain uv-run process natively.
    threading.Timer(0.2, os._exit, args=(0,)).start()
    return {"bye": True}


@app.get("/ui-status")
def ui_status():
    """Boot state for the demo page's own top bar. Session-free by design.

    /status is session-guarded and 409s a foreign session. A hosted demo
    claims the instance for the PARENT page's session and then iframes /ui, so
    the iframe polling /status would be exactly that foreign session and the
    bar would sit on BOOTING forever. This exposes strictly what the bar
    already renders to whoever is looking at the page.
    """
    log = state["log"]
    remaining = max(
        0,
        DEMO_SESSION_SECONDS
        - int(time.time() - (state["claimed_at"] or state["start"])),
    )
    return {
        "ready": state["ready"],
        "message": (
            f"Ready — {remaining // 60} min left in this session"
            if state["ready"]
            else (log[-1] if log else "Starting…")
        ),
    }


@app.get("/")
def root():
    return {"service": "robium demo gateway (vla-pick-and-place)"}


# dashboard.mount, not gr.mount_gradio_app: Gradio 6 takes the stylesheet here
# rather than on the Blocks constructor, and getting that wrong yields an
# unstyled, scrolling page with no error.
app = dashboard.mount(
    app,
    build_ui(
        lambda: state["worker"],
        # The bar reads the status dict in-process. Polling GET /status from
        # the browser instead would 409 the moment a hosted session claims the
        # instance: the iframe would be a second, foreign session.
        get_status=lambda: status(session=state["session"]),
    ),
    path="/ui",
    # Keeps the bar honest between page load and DEMO READY; stops polling the
    # moment the app reports ready.
    head=dashboard.boot_watch_js("/ui-status"),
)


def main() -> None:
    uvicorn.run(app, host="0.0.0.0", port=DEMO_PORT, log_level="info")


if __name__ == "__main__":
    main()
