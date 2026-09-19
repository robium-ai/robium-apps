from __future__ import annotations

import base64
from collections import deque
import io
import math
import secrets
import threading
import time

import gradio as gr
from PIL import Image

from act_aloha_cube_transfer.environment import JOINT_CONTROLS


def frame_html(frame) -> str:
    buffer = io.BytesIO()
    Image.fromarray(frame).save(buffer, format="JPEG", quality=90)
    payload = base64.b64encode(buffer.getvalue()).decode("ascii")
    return (
        '<div class="act-stream">'
        '<span class="act-stream-label">MuJoCo simulator · live top camera · 640×480</span>'
        f'<img src="data:image/jpeg;base64,{payload}" alt="Live ALOHA transfer-cube observation">'
        "</div>"
    )


def build_ui(runner) -> gr.Blocks:
    default_seed = int(runner.evidence["local"]["selected_seed"])
    default_frame = runner.preview(default_seed)
    stream_guard = threading.Lock()
    stream_generation = 0

    def advance_stream_generation() -> int:
        nonlocal stream_generation
        with stream_guard:
            stream_generation += 1
            return stream_generation

    def stream_is_current(generation: int) -> bool:
        with stream_guard:
            return generation == stream_generation

    def resolve_seed(value: float | None) -> int:
        if value is None or not math.isfinite(float(value)):
            raise gr.Error("Enter a finite integer seed.")
        seed = int(value)
        if seed < 0:
            raise gr.Error("Seed must be zero or greater.")
        return seed

    def preview(seed_value: float):
        seed = resolve_seed(seed_value)
        return frame_html(runner.preview(seed))

    def randomize():
        seed = 20_000 + secrets.randbelow(2_000_000_000)
        advance_stream_generation()
        runner.cancel()
        return seed, preview(seed), "layout randomized · restarting"

    def select_mode(mode: str, arm: str):
        manual = mode == "Manual control"
        advance_stream_generation()
        if manual:
            runner.cancel()
        else:
            runner.stop_manual()
        status_text = "starting manual control…" if manual else "pretrained ACT ready · horizon 100"
        return (
            gr.update(visible=manual),
            gr.update(visible=not manual),
            gr.update(visible=manual and arm == "Left arm"),
            gr.update(visible=manual and arm == "Right arm"),
            status_text,
        )

    def select_arm(arm: str):
        return gr.update(visible=arm == "Left arm"), gr.update(visible=arm == "Right arm")

    def cancel():
        runner.cancel()
        return "stopping after the current simulator action…"

    def stream_manual(mode_value: str, seed_value: float, *targets: float):
        if mode_value != "Manual control":
            yield gr.skip(), gr.skip()
            return
        generation = advance_stream_generation()
        seed = resolve_seed(seed_value)
        deadline = time.monotonic() + 5.0
        while True:
            try:
                runner.start_manual(seed, targets)
                break
            except RuntimeError:
                if time.monotonic() >= deadline:
                    yield gr.skip(), "manual control could not start"
                    return
                time.sleep(0.05)
        timestamps = deque(maxlen=31)
        try:
            for frame, _realized, rendered_at in runner.manual_frames():
                if not stream_is_current(generation):
                    return
                timestamps.append(float(rendered_at))
                if len(timestamps) > 1:
                    measured_fps = (len(timestamps) - 1) / (timestamps[-1] - timestamps[0])
                    health = f"live manual control · {measured_fps:.1f} FPS"
                else:
                    health = "live manual control · warming up"
                yield frame_html(frame), health
        finally:
            if stream_is_current(generation):
                runner.stop_manual()

    def update_manual_pose(seed_value: float, *targets: float):
        seed = resolve_seed(seed_value)
        try:
            runner.update_manual(seed, targets)
        except RuntimeError:
            return "manual control starting…"
        return "live manual control · target updated"

    def run_episode(seed_value: float):
        seed = resolve_seed(seed_value)
        horizon = 100
        runner.begin_run()
        yield frame_html(runner.preview(seed)), "starting…"
        for event in runner.run(seed=seed, execution_horizon=horizon):
            if event.done:
                if event.aborted:
                    state = "Stopped"
                elif event.success:
                    state = "Transfer complete"
                else:
                    state = "Partial progress"
            else:
                state = "Running"
            status = (
                f"{state.lower()} · step {event.step} · {event.phase} · "
                f"inference {event.inference_s * 1000:.0f} ms"
            )
            yield frame_html(event.frame), status

    with gr.Blocks(title="ACT ALOHA Cube Transfer · Robium", elem_classes="act-shell") as blocks:
        with gr.Row(elem_classes="act-body"):
            with gr.Column(scale=0, min_width=300, elem_classes="act-controls"):
                mode = gr.Radio(
                    choices=["Manual control", "Pretrained ACT model"],
                    value="Manual control",
                    label="Mode",
                    elem_classes="act-mode-toggle",
                )
                seed = gr.State(default_seed)
                random_button = gr.Button("Randomize layout")

                with gr.Column(elem_classes="act-mode-content"):
                    with gr.Column(visible=True, elem_classes="act-mode-panel") as manual_panel:
                        arm = gr.Radio(
                            choices=["Left arm", "Right arm"],
                            value="Left arm",
                            label="Arm",
                            elem_classes="act-arm-toggle",
                        )
                        manual_sliders = []
                        arm_panels = []
                        for index, joint_specs in enumerate((JOINT_CONTROLS[:7], JOINT_CONTROLS[7:])):
                            with gr.Column(visible=index == 0, elem_classes="act-arm-panel") as arm_panel:
                                for label, minimum, maximum, default in joint_specs:
                                    slider = gr.Slider(
                                        minimum=minimum,
                                        maximum=maximum,
                                        value=default,
                                        step=0.01,
                                        label=label,
                                        elem_classes="act-joint-slider",
                                    )
                                    manual_sliders.append(slider)
                            arm_panels.append(arm_panel)

                    with gr.Column(visible=False, elem_classes="act-mode-panel") as policy_panel:
                        gr.HTML('<div class="act-section">Pretrained policy</div>')
                        gr.Markdown(
                            "**Official LeRobot ACT · 80k steps**  \n"
                            "Runs the complete **100/100 action horizon**."
                        )
                        with gr.Row():
                            run_button = gr.Button("Run pretrained model", variant="primary")
                            stop_button = gr.Button("Stop")
                status = gr.Textbox(
                    value="starting manual control…",
                    label="Health",
                    interactive=False,
                    elem_classes="act-health",
                )
            with gr.Column(scale=1, min_width=0, elem_classes="act-main"):
                frame = gr.HTML(value=frame_html(default_frame), elem_classes="act-frame")

        manual_inputs = [mode, seed, *manual_sliders]
        random_event = random_button.click(randomize, outputs=[seed, frame, status])
        mode_event = mode.change(
            select_mode,
            inputs=[mode, arm],
            outputs=[manual_panel, policy_panel, *arm_panels, status],
            queue=False,
        )
        random_event.then(
            stream_manual,
            inputs=manual_inputs,
            outputs=[frame, status],
            concurrency_limit=None,
        )
        mode_event.then(
            stream_manual,
            inputs=manual_inputs,
            outputs=[frame, status],
            concurrency_limit=None,
        )
        arm.change(select_arm, inputs=[arm], outputs=arm_panels, queue=False)
        run_outputs = [frame, status]
        run_button.click(run_episode, inputs=[seed], outputs=run_outputs, api_name="run_episode")
        stop_button.click(cancel, outputs=[status], queue=False, api_name="cancel_episode")
        blocks.load(
            stream_manual,
            inputs=manual_inputs,
            outputs=[frame, status],
            api_name="stream_manual",
            concurrency_limit=None,
        )
        for slider in manual_sliders:
            slider.input(update_manual_pose, inputs=[seed, *manual_sliders], outputs=[status], queue=False)
    return blocks
