"""Small Gradio control surface for the SimulationManager."""

from __future__ import annotations

import gradio as gr

from typing import Protocol


class SimulationControls(Protocol):
    @property
    def robot_choices(self) -> tuple[str, ...]: ...

    @property
    def initial_robot_label(self) -> str: ...

    def actions_for(self, robot: str) -> tuple[str, ...]: ...

    def load_robot(self, robot: str) -> str: ...

    def move(self, vx: float, wz: float) -> str: ...

    def stop(self) -> str: ...

    def set_speed(self, speed: float) -> str: ...

    def reset(self) -> str: ...

    def action(self, name: str) -> str: ...


CSS = """
.gradio-container {
  max-width: 390px !important;
  margin: 0 auto !important;
  padding: 8px 10px 12px !important;
  font-size: 0.9rem !important;
}
.gradio-container .gap { gap: 8px !important; }
.gradio-container button { min-height: 36px !important; font-size: 0.9rem !important; }
.hero { text-align: center; margin-bottom: 0 !important; }
.hero h1 { font-size: 1.4rem !important; margin: 0 !important; }
.hero p { font-size: 0.85rem !important; margin: 0.1rem 0 0.25rem !important; }
.section-label p { margin: 0.1rem 0 !important; }
.field-row {
  display: grid !important;
  grid-template-columns: 66px minmax(0, 1fr) !important;
  align-items: center !important;
  gap: 8px !important;
}
.field-row > * { width: auto !important; min-width: 0 !important; }
.inline-label { min-width: 66px !important; }
.inline-label p {
  display: inline-block;
  margin: 0 !important;
  padding: 0.28rem 0.5rem;
  border-radius: 0.45rem;
  background: #dbeafe;
  color: #2563eb;
  font-weight: 700;
}
.viewer-tip p {
  margin: 0.15rem 0 0 !important;
  color: #64748b;
  font-size: 0.78rem !important;
  line-height: 1.35;
  text-align: center;
}
.arrow button { min-height: 36px !important; font-size: 1.1rem !important; }
.stop button { min-height: 36px !important; }
"""


def build_control_ui(manager: SimulationControls) -> gr.Blocks:
    initial_robot = manager.initial_robot_label
    initial_actions = manager.actions_for(initial_robot)

    with gr.Blocks(title="Robot Zoo Controller") as demo:
        gr.Markdown(
            "# Robot Zoo\nControl the robot here; inspect the simulation in MuJoCo.",
            elem_classes="hero",
        )

        with gr.Row(equal_height=True, elem_classes="field-row"):
            gr.Markdown("Robot", elem_classes="inline-label", min_width=66)
            robot = gr.Dropdown(
                choices=manager.robot_choices,
                value=initial_robot,
                show_label=False,
                container=False,
                interactive=True,
                scale=4,
            )
        load = gr.Button("Load", variant="primary")

        gr.Markdown(
            "**Movement** · continues until **Stop**",
            elem_classes="section-label",
        )
        with gr.Row(equal_height=True):
            gr.Column(scale=1, min_width=60)
            up = gr.Button("↑", elem_classes="arrow", scale=1, min_width=80)
            gr.Column(scale=1, min_width=60)
        with gr.Row(equal_height=True):
            left = gr.Button("←", elem_classes="arrow", min_width=80)
            stop = gr.Button(
                "Stop", variant="stop", elem_classes="stop", min_width=100
            )
            right = gr.Button("→", elem_classes="arrow", min_width=80)
        with gr.Row(equal_height=True):
            gr.Column(scale=1, min_width=60)
            down = gr.Button("↓", elem_classes="arrow", scale=1, min_width=80)
            gr.Column(scale=1, min_width=60)

        speed = gr.Slider(
            minimum=0.1,
            maximum=1.0,
            value=0.5,
            step=0.1,
            label="Speed",
        )

        with gr.Row(equal_height=True, elem_classes="field-row"):
            gr.Markdown("Action", elem_classes="inline-label", min_width=66)
            action = gr.Dropdown(
                choices=initial_actions,
                value=initial_actions[0],
                show_label=False,
                container=False,
                interactive=True,
                scale=4,
            )
        run_action = gr.Button("Run action")

        with gr.Row():
            reset = gr.Button("Reset robot", scale=1)
            status = gr.Textbox(
                value=f"{initial_robot} is running in MuJoCo.",
                show_label=False,
                container=False,
                interactive=False,
                scale=3,
            )
        gr.Markdown(
            "**MuJoCo mouse:** double-click a body to select · "
            "Ctrl-drag to rotate · Ctrl-right-drag to move · F1 for help",
            elem_classes="viewer-tip",
        )

        def action_update(selected_robot: str):
            choices = manager.actions_for(selected_robot)
            return gr.update(choices=choices, value=choices[0])

        def load_robot(selected_robot: str):
            message = manager.load_robot(selected_robot)
            return message, action_update(selected_robot)

        robot.change(action_update, inputs=robot, outputs=action)
        load.click(load_robot, inputs=robot, outputs=(status, action))
        up.click(lambda: manager.move(vx=1.0, wz=0.0), outputs=status)
        down.click(lambda: manager.move(vx=-1.0, wz=0.0), outputs=status)
        left.click(lambda: manager.move(vx=0.0, wz=1.0), outputs=status)
        right.click(lambda: manager.move(vx=0.0, wz=-1.0), outputs=status)
        stop.click(manager.stop, outputs=status)
        speed.change(manager.set_speed, inputs=speed, outputs=status)
        run_action.click(manager.action, inputs=action, outputs=status)
        reset.click(manager.reset, outputs=status)

    return demo


def launch_control_ui(
    manager: SimulationControls,
    *,
    inbrowser: bool = True,
    server_port: int | None = None,
) -> tuple[gr.Blocks, str]:
    demo = build_control_ui(manager)
    _, local_url, _ = demo.launch(
        inbrowser=inbrowser,
        prevent_thread_lock=True,
        server_name="127.0.0.1",
        server_port=server_port,
        share=False,
        quiet=True,
        show_error=True,
        footer_links=[],
        theme=gr.themes.Soft(primary_hue="blue", neutral_hue="slate"),
        css=CSS,
    )
    print(f"Gradio controller: {local_url}", flush=True)
    return demo, local_url
