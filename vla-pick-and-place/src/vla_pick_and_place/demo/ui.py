"""The demo's Gradio app: a robium workspace — cameras left, controls right.

Mounted at /ui by gateway.py; a hosted demo iframes it. Layout comes from the
vendored `dashboard.py`/`dashboard.css` (source: shared/rerun-dashboard), so a
visitor moving between the ROS navigation demo and this one sees one product.

The page offers exactly two things, because exactly two things work:

  * **Drive the arm.** Six sliders are the environment's action space —
    absolute joint angles in radians, bounded by the real actuator limits. The
    vector you dial in is the vector `step()` receives; nothing rewrites it,
    and the reward, grasp flags, and success come straight out of `info`.
  * **Watch a demonstration.** A recorded episode from the pinned, verified
    dataset, replayed frame by frame. It calls no `step()` and runs no policy.

A third thing a visitor might expect — running a trained controller — is
listed with the reason it is unavailable rather than faked.
`policy/controllers.py` owns that text; this file only renders it.

**Why this page does not embed Rerun.** It used to, and the embedded viewer
rendered a black canvas. Measured, not guessed: the recording bytes are a
valid RRF2 stream (85 KB with real image data, readable off disk), the Gradio
media-stream chunks are fetched by the browser with 200s, `gradio_rerun`
reports "Rerun viewer ready" and "Adding new log receiver", wgpu initialises,
and no error appears in the console — and the canvas stays black through both
an initial `value=` and a `blocks.load` stream. Shipping that panel would mean
shipping a demo whose main surface shows nothing, so this page renders the
frames directly instead. Rerun is still the offline surface and still works
there: `./app sim` and `./app play` write .rrd files that open correctly in
the desktop viewer, which is where scrubbing a timeline actually belongs.

One layout rule learned the hard way, which produced a page that looked broken
with no error in the console: **every child of the rail is a `.rd-section`.**
Wrapping sections in an extra `gr.Column` to show/hide a mode inherits
Gradio's flex rules on the rail's main axis and the wrapper collapses — the
controls sit in the DOM, visible:visible, at full size, off screen. So there
is no mode toggle: the two buttons *are* the two modes, each in its own
labelled section, and the source strip over the readout says which one
produced the frames on screen.
"""

from __future__ import annotations

import time

import gradio as gr
import numpy as np

from vla_pick_and_place.config import (
    DEMO_SIM_SEEDS,
    ENV_ID,
    EXPLORE_STEPS,
    JOINT_NAMES,
    NEXUS_VERSION,
    TASK,
)
from vla_pick_and_place.data import datasets
from vla_pick_and_place.demo.dashboard import (
    bar_html,
    note,
    rail,
    section,
    split,
    top_bar,
    workspace,
)
from vla_pick_and_place.env.contract import (
    ACTION_HIGH,
    ACTION_LOW,
    clamp_to_action_range,
)
from vla_pick_and_place.policy import controllers

# Slider bounds, rounded INWARD from the measured actuator range. Rounding
# inward matters: a bound rounded outward is a value the simulator will reject,
# and Gradio renders the raw float, so the un-rounded -1.9198600053787231 also
# reads as noise in a 360px rail. Actions are clipped to the TRUE range inside
# the worker before they reach the simulator, so a rounded slider bound can
# never widen what gets sent.
SLIDER_LOW = tuple(float(np.ceil(v * 1000) / 1000) for v in ACTION_LOW)
SLIDER_HIGH = tuple(float(np.floor(v * 1000) / 1000) for v in ACTION_HIGH)

# How often a run pushes a new frame to the browser. Every control step would
# re-encode two PNGs per step and starve the run loop; every 4th is smooth to
# watch and keeps the numbers moving.
SIM_FRAME_STRIDE = 4
DATASET_FRAME_STRIDE = 8

DRIVE_NOTE = (
    "These six sliders are this environment's action space: absolute joint "
    "angles in radians, bounded by the real actuator limits. What you set is "
    f"what <code>{ENV_ID}</code> is stepped with. The reward, grasp state and "
    "success shown under the cameras come from the simulator, not from this "
    "page."
)

DATASET_NOTE = (
    f"Recorded episodes from <code>{datasets.PRIMARY.repo_id}</code>, pinned at "
    f"<code>{datasets.PRIMARY.revision[:8]}</code>. This is playback: no "
    "simulation step runs and no policy is involved. Joint numbers are in the "
    "dataset's own units (degrees, gripper as percent of travel), not the "
    "simulator's radians."
)

TASK_NOTE = (
    f"The task these demonstrations record: <code>{TASK}</code>. It is dataset "
    "metadata. Nothing on this page is language-conditioned, so changing the "
    "wording would change nothing — the box is not offered."
)

RERUN_NOTE = (
    "<code>./app sim</code> and <code>./app play</code> write the same runs to "
    "Rerun <code>.rrd</code> files under <code>outputs/viz/</code>, with the "
    "cameras, joint state, action and reward on one scrubbable timeline. Open "
    "one with <code>uv run rerun outputs/viz/&lt;file&gt;.rrd</code>."
)


def _controller_note() -> str:
    lines = [
        "<b>No trained controller is available.</b> Each registered one, and "
        "why it cannot run here:"
    ]
    for c in controllers.REGISTRY.values():
        lines.append(f"<br><br><b>{c.label}</b><br>{c.unavailable_reason}")
    return "".join(lines)


def _meta() -> dict[str, str]:
    return {"env": f"so101-nexus {NEXUS_VERSION}", "id": ENV_ID}


def _readout(frame) -> str:
    """The numbers behind the picture: per-joint state and action, plus info.

    Rendered from the frame itself rather than from remembered UI state, so
    what is on screen is always what the last step actually produced.
    """
    reward = "—" if frame.reward is None else f"{frame.reward:+.5f}"
    success = (
        '<b class="rd-ok">SUCCESS</b>' if frame.success else "<b>no success</b>"
    )
    grasped = "grasped" if frame.info.get("is_grasped") else "not grasped"
    dist = frame.info.get("obj_to_target_dist")
    dist_cell = f"{float(dist):.3f} m" if dist is not None else "—"

    rows = "".join(
        f"<tr><td>{name}</td><td>{s:+.4f}</td><td>{a:+.4f}</td></tr>"
        for name, s, a in zip(JOINT_NAMES, frame.state, frame.action)
    )
    return f"""
<div class="rd-readout">
  <div class="rd-src">
    <span>source <b>{frame.source}</b></span>
    <span>step {frame.step}/{frame.total}</span>
    <span>units {frame.units}</span>
    <span>{grasped}</span>
    <span>object&rarr;target {dist_cell}</span>
    <span>reward {reward}</span>
    <span>{success}</span>
  </div>
  <table>
    <tr><th>joint</th><th>state</th><th>action</th></tr>
    {rows}
  </table>
</div>
""".strip()


def _slider_values(state):
    """Joint state clamped to the SLIDER bounds, not the actuator bounds.

    The sliders round the actuator range inward for display, so a value that
    is legal for the simulator can still be a hair outside the widget's
    minimum — Gradio rejects that outright rather than clamping.
    """
    return clamp_to_action_range(state, SLIDER_LOW, SLIDER_HIGH)


def _images(frame):
    """Overhead and wrist frames as the UI shows them.

    Dataset playback has both cameras; a source that lacked one would leave
    the panel empty rather than reuse a stale image from another run.
    """
    return (
        None if frame.overhead is None else np.asarray(frame.overhead),
        None if frame.wrist is None else np.asarray(frame.wrist),
    )


def build_ui(get_worker, get_status=None) -> gr.Blocks:
    """`get_worker` -> SimWorker | None (None while the gateway boots).

    `get_status` -> the gateway's status dict, or None. Read in-process rather
    than fetched from /status by the browser: once a hosted session claims the
    instance, /status answers 409 to any other session, and the iframe polling
    its own gateway would be exactly that other session.
    """

    def _bar(state: str, phase: str, message: str) -> str:
        return bar_html(state=state, phase=phase, message=message, meta=_meta())

    def initial_bar() -> dict:
        status = get_status() if get_status else None
        if status and status.get("ready"):
            minutes = max(0, -(-status.get("remaining_s", 0) // 60))
            return dict(
                state="ready",
                phase="READY",
                message=f"Ready — {minutes} min left in this session",
            )
        log = (status or {}).get("log") or []
        return dict(
            state="booting",
            phase="BOOTING",
            message=log[-1] if log else "Starting the simulator…",
        )

    def _await_worker(timeout: float = 90.0):
        """Wait out the gateway's boot rather than erroring on a fast page load."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            worker = get_worker()
            if worker is not None:
                return worker
            time.sleep(0.5)
        return None

    def _require_worker():
        worker = get_worker()
        if worker is None:
            raise gr.Error("Still starting — the simulator is coming up (see the status bar).")
        return worker

    # --- handlers ------------------------------------------------------------

    def first_frame():
        """Show one real reset frame at page load.

        Deliberately the same code path a Reset click takes: if this renders,
        the surface is known-good before the visitor touches anything, and a
        blank panel is a failure that shows up immediately rather than after
        the first interaction.
        """
        worker = _await_worker()
        if worker is None:
            yield (
                None,
                None,
                "",
                "Simulator did not start — check the gateway log.",
                _bar("failed", "FAILED", "simulator did not start"),
                *[gr.update() for _ in JOINT_NAMES],
            )
            return
        frame = worker.reset(seed=DEMO_SIM_SEEDS[0])
        overhead, wrist = _images(frame)
        target = frame.info.get("target_object", "the cube")
        yield (
            overhead,
            wrist,
            _readout(frame),
            f"Reset at seed {DEMO_SIM_SEEDS[0]} — carry {target} to the disc.",
            _bar("ready", "READY", f"Reset — carry {target} to the disc"),
            *[gr.update(value=v) for v in _slider_values(frame.state)],
        )

    def reset_sim(seed):
        worker = _require_worker()
        frame = worker.reset(seed=int(seed))
        overhead, wrist = _images(frame)
        target = frame.info.get("target_object", "the cube")
        return (
            overhead,
            wrist,
            _readout(frame),
            f"Reset at seed {int(seed)} — carry {target} to the disc.",
            _bar("ready", "READY", f"Reset at seed {int(seed)}"),
            *[gr.update(value=v) for v in _slider_values(frame.state)],
        )

    def drive(n_steps, *targets):
        worker = _require_worker()
        yield (
            gr.update(),
            gr.update(),
            gr.update(),
            "sending joint targets to the simulator…",
            _bar("running", "RUNNING", "driving the arm"),
        )
        last = None
        for frame in worker.drive(targets, n_steps=int(n_steps)):
            last = frame
            if frame.step % SIM_FRAME_STRIDE == 0 or frame.done:
                overhead, wrist = _images(frame)
                yield (
                    overhead,
                    wrist,
                    _readout(frame),
                    f"step {frame.step} — reward {frame.reward:+.5f}",
                    _bar("running", "RUNNING", f"step {frame.step}"),
                )
        if last is None:
            yield (
                gr.update(),
                gr.update(),
                gr.update(),
                "run stopped",
                _bar("failed", "READY", "run stopped"),
            )
            return
        verdict = (
            "Cube on the disc — the simulator reports success"
            if last.success
            else f"Held for {int(n_steps)} steps — the simulator reports no success"
        )
        overhead, wrist = _images(last)
        yield overhead, wrist, _readout(last), verdict, _bar("ready", "READY", verdict)

    def play_episode(episode):
        from vla_pick_and_place.demo.session import dataset_frames

        yield (
            gr.update(),
            gr.update(),
            gr.update(),
            f"loading recorded episode {int(episode)}…",
            _bar("running", "RUNNING", "loading the recording"),
        )
        player = datasets.EpisodePlayer(datasets.PRIMARY, episode=int(episode))
        last = None
        for frame in dataset_frames(player, stride=DATASET_FRAME_STRIDE):
            last = frame
            overhead, wrist = _images(frame)
            yield (
                overhead,
                wrist,
                _readout(frame),
                f"recorded frame {frame.step}/{frame.total}",
                _bar("running", "RUNNING", f"replaying {frame.step}/{frame.total}"),
            )
        if last is None:
            yield (
                None,
                None,
                "",
                "that episode had no frames",
                _bar("failed", "READY", "that episode had no frames"),
            )
            return
        verdict = f"Recorded episode {int(episode)} replayed — {last.total} frames"
        # Re-send the last frame rather than a no-op update, so the page ends
        # showing the numbers behind the picture it is showing.
        overhead, wrist = _images(last)
        yield overhead, wrist, _readout(last), verdict, _bar("ready", "READY", verdict)

    # --- layout --------------------------------------------------------------

    with workspace("vla-pick-and-place — robium demo") as blocks:
        bar = top_bar(meta=_meta(), **initial_bar())

        with split():
            with gr.Column(elem_classes=["rd-viewer"]):
                with gr.Row(elem_classes=["rd-cams"]):
                    with gr.Column(elem_classes=["rd-cam"]):
                        gr.HTML(
                            '<p class="rd-cam-label">overhead camera</p>', padding=False
                        )
                        overhead_img = gr.Image(
                            show_label=False,
                            interactive=False,
                            # Gradio 6 replaced the per-button flags with one
                            # `buttons` list; [] is "no hover toolbar".
                            buttons=[],
                            container=False,
                        )
                    with gr.Column(elem_classes=["rd-cam"]):
                        gr.HTML(
                            '<p class="rd-cam-label">wrist camera</p>', padding=False
                        )
                        wrist_img = gr.Image(
                            show_label=False,
                            interactive=False,
                            # Gradio 6 replaced the per-button flags with one
                            # `buttons` list; [] is "no hover toolbar".
                            buttons=[],
                            container=False,
                        )
                readout = gr.HTML("", padding=False)

            with rail():
                with section("task"):
                    note(TASK_NOTE)

                with section("drive the arm — live simulator"):
                    sliders = [
                        gr.Slider(
                            minimum=low,
                            maximum=high,
                            value=0.0,
                            step=0.01,
                            label=name,
                        )
                        for name, low, high in zip(JOINT_NAMES, SLIDER_LOW, SLIDER_HIGH)
                    ]
                    hold_steps = gr.Slider(
                        minimum=4,
                        maximum=EXPLORE_STEPS,
                        value=48,
                        step=4,
                        label="control steps to hold",
                    )
                    send_btn = gr.Button("Send joint targets", variant="primary")
                    note(DRIVE_NOTE)

                with section("reset"):
                    seed = gr.Slider(
                        minimum=0,
                        maximum=max(DEMO_SIM_SEEDS),
                        value=DEMO_SIM_SEEDS[0],
                        step=1,
                        label="reset seed",
                    )
                    reset_btn = gr.Button("Reset simulator")

                with section("watch a demonstration — recorded"):
                    episode = gr.Slider(
                        minimum=0,
                        maximum=datasets.PRIMARY.episodes - 1,
                        value=0,
                        step=1,
                        label="episode",
                    )
                    play_btn = gr.Button("Play demonstration", variant="primary")
                    note(DATASET_NOTE)

                with section("trained controllers"):
                    note(_controller_note())

                with section("rerun timeline"):
                    note(RERUN_NOTE)

                with section("status"):
                    status = gr.Textbox(
                        value="Starting the simulator…",
                        show_label=False,
                        interactive=False,
                        elem_classes=["rd-log"],
                        lines=3,
                        max_lines=3,
                    )

        view = [overhead_img, wrist_img, readout, status, bar]
        blocks.load(first_frame, outputs=[*view, *sliders])
        reset_btn.click(
            reset_sim, inputs=[seed], outputs=[*view, *sliders], api_name="reset_sim"
        )
        send_btn.click(
            drive, inputs=[hold_steps, *sliders], outputs=view, api_name="drive"
        )
        play_btn.click(
            play_episode, inputs=[episode], outputs=view, api_name="play_episode"
        )

    return blocks
