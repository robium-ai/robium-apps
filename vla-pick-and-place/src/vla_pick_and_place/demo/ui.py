"""The demo's Gradio app: a robium workspace — Rerun left, controls right.

Mounted at /ui by gateway.py (gr.mount_gradio_app); a hosted demo iframes it.
Built against gradio_rerun 0.34.1's streaming pattern (verified 2026-07-15
from rerun-io/gradio-rerun-viewer's README): each Run constructs a fresh
RecordingStream, logs into it, and yields `stream.read()` bytes to the
`Rerun(streaming=True)` component.

Layout comes from the vendored `dashboard.py`/`dashboard.css` (source:
shared/rerun-dashboard) — one viewport tall, never scrolls, the viewer takes
every pixel the bar and rail do not. The palette is robot-navigation's, so a
visitor moving between the ROS demo and this one sees one product.

The controller descriptions state what each controller reads and pin the
included checkpoint's current evaluation result. The checkpoint id stays in
the top bar so a new model can be verified without digging through logs.
"""

import uuid
from functools import lru_cache
import os
from pathlib import Path
import tempfile

import numpy as np

import gradio as gr
import rerun as rr
import rerun.blueprint as rrb
from gradio_rerun import Rerun

from vla_pick_and_place.config import DEMO_CHECKPOINT, INFERENCE_DEVICE, TASK
from vla_pick_and_place.demo.dashboard import (
    bar_html,
    note,
    rail,
    section,
    split,
    top_bar,
    workspace,
)

APP_ID = "vla_pick_and_place_demo"

CONTROLLER_CHOICES = [
    ("Scripted controller — task reference", "oracle"),
    ("SmolVLA checkpoint — 100 steps", "trained"),
]

CONTROLLER_NOTE = (
    "The scripted controller reads simulator state and follows a fixed motion "
    "sequence. SmolVLA reads the two cameras and your instruction. "
    "<b>Current checkpoint result: 0/10 successful evaluation episodes.</b>"
)

TASK_NOTE = (
    f"Training instruction: <code>{TASK}</code>. Use this wording when "
    "evaluating the included checkpoint."
)

# Bar meta: permanently visible, because both facts qualify everything the
# page shows. The checkpoint is the reason "trained" fails; the device is why
# a step takes as long as it does.
def _meta() -> dict[str, str]:
    return {"ckpt": DEMO_CHECKPOINT, "device": INFERENCE_DEVICE}


def _blueprint() -> rrb.Blueprint:
    return rrb.Blueprint(
        rrb.Vertical(
            rrb.Horizontal(
                rrb.Spatial2DView(origin="camera/scene", name="scene camera"),
                rrb.Spatial2DView(origin="camera/wrist", name="wrist camera"),
            ),
            rrb.Horizontal(
                rrb.TimeSeriesView(origin="state", name="joint state"),
                rrb.TimeSeriesView(origin="action", name="action sent"),
            ),
            row_shares=[3, 2],
        ),
        collapse_panels=True,
    )


@lru_cache(maxsize=1)
def _preview_recording() -> Path:
    """Return one real reset frame so the viewer is useful before Run.

    The environment is created and closed in this call because MuJoCo's CGL
    context is thread-affine on macOS. The preview uses the same entity paths
    and blueprint as a live episode, so the first streamed run replaces it
    cleanly instead of changing layouts.
    """
    from vla_pick_and_place.demo.episode_runner import _log_step
    from vla_pick_and_place.env.so101_pick import SO101PickEnv

    rec = rr.RecordingStream(
        application_id=APP_ID,
        recording_id="vla-pick-and-place-preview",
    )
    path = Path(tempfile.gettempdir()) / f"vla-pick-and-place-preview-{os.getpid()}.rrd"
    rec.save(path, default_blueprint=_blueprint())
    env = SO101PickEnv(task=TASK)
    try:
        obs, _ = env.reset(seed=0)
        action = np.zeros_like(obs["observation.state"], dtype=np.float32)
        _log_step(rec, 0, obs, action, task=TASK)
        rec.flush()
        return path
    finally:
        env.close()


def build_ui(get_runner, get_status=None) -> gr.Blocks:
    """`get_runner` -> EpisodeRunner | None (None while the gateway boots).

    `get_status` -> the gateway's status dict, or None. Read in-process rather
    than fetched from /status by the browser: once a hosted session claims the
    instance, /status answers 409 to any other session, and the iframe polling
    its own gateway would be exactly that other session.
    """

    def _bar(state: str, phase: str, message: str) -> str:
        return bar_html(state=state, phase=phase, message=message, meta=_meta())

    def initial_bar() -> dict:
        """Bar state at page render, so a page loaded after boot says READY.

        While the model is still loading, `boot_watch_js` in the page head
        takes over and polls /ui-status until ready. Every update after that
        is a return value from the handler that caused it.
        """
        status = get_status() if get_status else None
        if status and status.get("ready"):
            minutes = max(0, -(-status.get("remaining_s", 0) // 60))
            return dict(state="ready", phase="READY",
                        message=f"Ready — {minutes} min left in this session")
        log = (status or {}).get("log") or []
        return dict(state="booting", phase="BOOTING",
                    message=log[-1] if log else "Loading the model…")

    def run_episode(controller: str, instruction: str):
        runner = get_runner()
        if runner is None:
            raise gr.Error("Still booting — the model is loading (see the status bar).")
        instruction = (instruction or "").strip() or TASK

        # A FRESH recording id per Run. Reusing one id makes the viewer MERGE
        # runs (gradio_rerun's documented same-id behavior): the second
        # episode re-logs step 0..N onto the first's timeline, the playhead
        # stays parked at the old end, and the viewer looks frozen while the
        # status counter advances. One id per episode = every run starts a
        # clean timeline the viewer jumps to.
        rec = rr.RecordingStream(application_id=APP_ID, recording_id=str(uuid.uuid4()))
        stream = rec.binary_stream()
        rec.send_blueprint(_blueprint())
        yield stream.read(), f"resetting env — {controller} episode starting…", _bar(
            "running", "RUNNING", f"{controller} episode starting…"
        )

        print(f"[demo] run_episode start: controller={controller} instruction={instruction!r}", flush=True)
        try:
            for ev in runner.run(controller, instruction, rec):
                if ev.step % 50 == 0 or ev.done:
                    print(f"[demo] step {ev.step} done={ev.done} success={ev.success}", flush=True)
                if ev.done:
                    if ev.aborted:
                        verdict = "Run stopped after the workspace changed sessions"
                        state = "failed"
                    elif ev.success:
                        verdict = "Cube placed in the bin"
                        state = "ready"
                    elif controller == "trained":
                        verdict = "Task not completed by the included checkpoint"
                        state = "ready"
                    else:
                        verdict = "Scripted controller did not complete the task"
                        state = "failed"
                    yield stream.read(), f"finished at step {ev.step + 1}: {verdict}", _bar(
                        state, "READY", verdict
                    )
                else:
                    yield stream.read(), f"step {ev.step + 1}/{ev.total}", _bar(
                        "running", "RUNNING", f"step {ev.step + 1}/{ev.total}"
                    )
        except RuntimeError as e:  # run lock held — another episode is executing
            raise gr.Error(str(e))

    with workspace("vla-pick-and-place — robium demo") as blocks:
        bar = top_bar(meta=_meta(), **initial_bar())

        with split():
            viewer = Rerun(
                value=_preview_recording,
                streaming=True,
                # "100%", never a pixel count: an int pins the height and the
                # viewer stops filling the split.
                height="100%",
                elem_classes=["rd-viewer"],
                panel_states={"time": "collapsed", "blueprint": "hidden", "selection": "hidden"},
            )

            with rail():
                with section("instruction"):
                    instruction = gr.Textbox(
                        value=TASK, show_label=False, lines=2,
                        placeholder="what should the arm do?",
                    )
                    note(TASK_NOTE)

                with section("controller"):
                    controller = gr.Radio(
                        choices=CONTROLLER_CHOICES, value="oracle", show_label=False,
                    )
                    note(CONTROLLER_NOTE)

                with section("run"):
                    run_btn = gr.Button("Run episode", variant="primary")

                with section("status"):
                    status = gr.Textbox(
                        value="Ready to run", show_label=False, interactive=False,
                        elem_classes=["rd-log"], lines=3, max_lines=3,
                    )

        run_btn.click(
            run_episode,
            inputs=[controller, instruction],
            outputs=[viewer, status, bar],
            api_name="run_episode",
        )

    return blocks
