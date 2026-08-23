from __future__ import annotations

import base64
import html
import io
import math
import secrets
import uuid

import gradio as gr
import rerun as rr
from gradio_rerun import Rerun
from PIL import Image

from act_aloha_cube_transfer.telemetry import blueprint, log_event

APP_ID = "act_aloha_cube_transfer_demo"


def frame_html(frame) -> str:
    buffer = io.BytesIO()
    Image.fromarray(frame).save(buffer, format="JPEG", quality=90)
    payload = base64.b64encode(buffer.getvalue()).decode("ascii")
    return (
        '<div class="act-stream">'
        '<span class="act-stream-label">Live top camera · 640×480</span>'
        f'<img src="data:image/jpeg;base64,{payload}" alt="Live ALOHA transfer-cube observation">'
        "</div>"
    )


def result_html(*, state: str, text: str, seed: int, horizon: int) -> str:
    return (
        '<div class="act-result">'
        f"<strong>{html.escape(state)}</strong><br>{html.escape(text)}<br>"
        f'<span class="act-note">seed {seed} · execute {horizon}/100 predicted actions</span>'
        "</div>"
    )


def evidence_markdown(evidence: dict) -> str:
    published = evidence["published"]
    local = evidence["local"]
    successes = sum(bool(item["success"]) for item in local["episodes"])
    return (
        "| evidence | source | episodes | success |\n"
        "| --- | --- | ---: | ---: |\n"
        f"| Official ACT checkpoint | published LeRobot evaluation | {published['episodes']} | {published['success_rate']:.1%} |\n"
        f"| This Mac calibration | local MPS, horizon {local['execution_horizon']} | {len(local['episodes'])} | {successes / len(local['episodes']):.1%} |\n\n"
        f"The published result and local calibration are separate experiments. Seed **{local['selected_seed']}** "
        "was replayed successfully and is the default live example."
    )


def build_ui(runner) -> gr.Blocks:
    default_seed = int(runner.evidence["local"]["selected_seed"])
    default_horizon = int(runner.evidence["local"]["execution_horizon"])
    default_frame = runner.preview(default_seed)

    def resolve_seed(value: float | None) -> int:
        if value is None or not math.isfinite(float(value)):
            raise gr.Error("Enter a finite integer seed.")
        seed = int(value)
        if seed < 0:
            raise gr.Error("Seed must be zero or greater.")
        return seed

    def preview(seed_value: float, horizon: int):
        seed = resolve_seed(seed_value)
        return frame_html(runner.preview(seed)), result_html(
            state="Layout ready",
            text="Run this exact cube placement or choose another seed.",
            seed=seed,
            horizon=int(horizon),
        )

    def randomize(horizon: int):
        seed = 20_000 + secrets.randbelow(2_000_000_000)
        frame, result = preview(seed, horizon)
        return seed, frame, result

    def cancel():
        runner.cancel()
        return "stopping after the current simulator action…"

    def run_episode(seed_value: float, horizon: int):
        seed = resolve_seed(seed_value)
        horizon = int(horizon)
        runner.begin_run()
        recording = rr.RecordingStream(application_id=APP_ID, recording_id=str(uuid.uuid4()))
        stream = recording.binary_stream()
        recording.send_blueprint(blueprint())
        yield frame_html(runner.preview(seed)), "starting…", stream.read(), result_html(
            state="Starting",
            text="ACT is predicting the first 100-action chunk.",
            seed=seed,
            horizon=horizon,
        )
        for event in runner.run(seed=seed, execution_horizon=horizon):
            log_event(recording, event)
            if event.done:
                if event.aborted:
                    state = "Stopped"
                    text = f"Stopped at step {event.step}; highest simulator stage was {event.phase}."
                elif event.success:
                    state = "Transfer complete"
                    text = f"The left gripper received and lifted the cube at step {event.step}."
                else:
                    state = "Partial progress"
                    text = f"Episode ended at step {event.step}; highest simulator stage was {event.phase}."
            else:
                state = "Running"
                text = (
                    f"Step {event.step}/{event.total} · {event.phase} · policy call {event.policy_call} · "
                    f"chunk action {event.chunk_index + 1}/{horizon}."
                )
            status = (
                f"{state.lower()} · step {event.step} · {event.phase} · "
                f"inference {event.inference_s * 1000:.0f} ms"
            )
            yield frame_html(event.frame), status, stream.read(), result_html(
                state=state,
                text=text,
                seed=seed,
                horizon=horizon,
            )

    with gr.Blocks(title="ACT ALOHA Cube Transfer · Robium", elem_classes="act-shell") as blocks:
        gr.HTML(
            '<header class="act-topbar"><span class="act-brand">robium</span>'
            '<span class="act-title"><span class="act-dot"></span>ACT ALOHA Cube Transfer</span>'
            f'<span class="act-subtitle">{runner.device.upper()} · official ACT checkpoint · 100-action chunks</span></header>'
        )
        with gr.Row(elem_classes="act-body"):
            with gr.Column(scale=0, min_width=300, elem_classes="act-controls"):
                gr.HTML('<div class="act-section">Experiment controls</div>')
                gr.Markdown("**Policy**  \nOfficial LeRobot ACT · 80k steps · 83% published success")
                horizon = gr.Radio(
                    choices=[
                        ("Responsive · execute 25/100", 25),
                        ("Balanced · execute 50/100", 50),
                        ("Reference · execute 100/100", 100),
                    ],
                    value=default_horizon,
                    label="Execution horizon",
                )
                seed = gr.Number(value=default_seed, precision=0, label="Layout seed")
                with gr.Row():
                    random_button = gr.Button("Randomize layout")
                    replay_button = gr.Button("Replay this seed")
                with gr.Row():
                    run_button = gr.Button("Run rollout", variant="primary")
                    stop_button = gr.Button("Stop")
                status = gr.Textbox(value="ready", label="Health", interactive=False)
                gr.Markdown(
                    "ACT predicts 100 joint-action targets at once. The execution horizon controls how many are "
                    "used before the policy observes the scene and replans."
                )
            with gr.Column(scale=1, elem_classes="act-main"):
                frame = gr.HTML(value=frame_html(default_frame), elem_classes="act-frame")
                result = gr.HTML(
                    result_html(
                        state="Layout ready",
                        text="The default seed is a locally replayed successful transfer.",
                        seed=default_seed,
                        horizon=default_horizon,
                    )
                )
                gr.Markdown("### Evidence")
                gr.Markdown(evidence_markdown(runner.evidence))
                gr.Markdown("### Rerun timeline")
                viewer = Rerun(
                    streaming=True,
                    height=520,
                    panel_states={"time": "collapsed", "blueprint": "hidden", "selection": "hidden"},
                )
                gr.Markdown(
                    "The direct frame above is the primary live view. Rerun adds scrub-able camera, "
                    "reward-stage, 14D action, joint-state, and chunk-boundary timelines."
                )

        seed.change(preview, inputs=[seed, horizon], outputs=[frame, result])
        horizon.change(preview, inputs=[seed, horizon], outputs=[frame, result])
        random_button.click(randomize, inputs=[horizon], outputs=[seed, frame, result])
        run_outputs = [frame, status, viewer, result]
        run_button.click(run_episode, inputs=[seed, horizon], outputs=run_outputs, api_name="run_episode")
        replay_button.click(run_episode, inputs=[seed, horizon], outputs=run_outputs)
        stop_button.click(cancel, outputs=[status], queue=False, api_name="cancel_episode")
    return blocks
