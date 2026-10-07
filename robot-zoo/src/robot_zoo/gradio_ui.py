"""Small Gradio control surface for the SimulationManager."""

from __future__ import annotations

import gradio as gr
from pathlib import Path

from typing import Callable, Protocol


class SimulationControls(Protocol):
    @property
    def robot_choices(self) -> tuple[str, ...]: ...

    @property
    def initial_robot_label(self) -> str: ...

    def actions_for(self, robot: str) -> tuple[str, ...]: ...

    def load_robot(self, robot: str) -> str: ...

    def move(self, vx: float, wz: float) -> str: ...

    def teleop(self, robot: str, vx: float, vy: float, wz: float, action: str | None = None) -> str: ...

    def stop(self) -> str: ...

    def reset(self) -> str: ...

    def action(self, name: str) -> str: ...


CSS = """
html, body, .gradio-container { background:#232a31 !important; color:#e8edf1 !important; }
.gradio-container {
  width:100% !important; max-width:none !important; margin:0 !important; padding:4px 10px !important;
  --body-background-fill:#232a31; --body-background-fill-dark:#232a31;
  --block-background-fill:#29313a; --block-background-fill-dark:#29313a;
  --block-border-color:#3d4853; --block-border-color-dark:#3d4853;
  --input-background-fill:#29313a; --input-background-fill-dark:#29313a;
  --input-background-fill-focus:#303a45; --input-background-fill-focus-dark:#303a45;
  --input-background-fill-hover:#303a45; --input-background-fill-hover-dark:#303a45;
  --input-border-color-focus:#89dc9c; --input-border-color-focus-dark:#89dc9c;
  --background-fill-primary:#29313a; --background-fill-primary-dark:#29313a;
  --background-fill-secondary:#3b4c43; --background-fill-secondary-dark:#3b4c43;
  --border-color-primary:#46525e; --border-color-primary-dark:#46525e;
  --input-border-color:#46525e; --input-border-color-dark:#46525e;
  --body-text-color:#e8edf1; --body-text-color-dark:#e8edf1;
  --body-text-color-subdued:#acb9c6; --body-text-color-subdued-dark:#acb9c6;
  --block-label-text-color:#acb9c6; --block-label-text-color-dark:#acb9c6; --input-placeholder-color:#91a0ad;
  --button-secondary-background-fill:#303a45; --button-secondary-background-fill-dark:#303a45;
  --button-secondary-text-color:#e8edf1; --button-secondary-text-color-dark:#e8edf1;
}
.gradio-container .main { padding:0 !important; }
.gradio-container .column {gap:4px !important;}
#joystick-panel .html-container, #controller-brand .html-container {padding:0 !important;}
#controller-header { align-items:center; gap:10px !important; border-bottom:1px solid #3d4853; padding-bottom:10px; }
#controller-header > * { min-height:34px; }
#controller-brand { flex:0 0 150px !important; min-width:150px !important; }
.brand {display:flex;align-items:center;gap:10px;color:#f1f4f6;font:600 20px system-ui;white-space:nowrap;}
.brand-dot {width:10px;height:10px;background:#89dc9c;border-radius:50%;}
#controller-header button { min-width:64px; }
#pin-control {color:#a5e5b3 !important;}
#footer-controls {align-items:center;gap:16px !important;border-top:1px solid #3d4853;padding-top:6px;}
#footer-controls button {min-height:36px;white-space:nowrap;}
#command-status p {margin:0;color:#9eacb9;font-size:11px;}
#more-controls {padding:0 !important;border:1px solid #3d4853 !important;background:#29313a !important;border-radius:8px;}
#more-controls .label-wrap, #more-controls .label-wrap span {color:#b7c4d0 !important;}
#more-controls p {font-size:12px;color:#afbdca;}
@media(max-width:650px) {
  .gradio-container {padding:6px 10px !important;}
  .gradio-container .column {gap:5px !important;}
  #controller-header {gap:6px !important;padding-bottom:0;}
  #controller-brand {flex-basis:100px !important;min-width:100px !important;}
  .brand {font-size:15px;gap:6px;}
  #footer-controls {gap:10px !important;padding-top:3px;}
  #more-controls .label-wrap {padding:8px !important;}
}
"""

def build_control_ui(manager: SimulationControls, *, on_pin: Callable[[bool], None] | None = None) -> gr.Blocks:
    initial_robot = manager.initial_robot_label
    initial_actions = manager.actions_for(initial_robot)

    with gr.Blocks(title="Robot Zoo Controller") as demo:
        with gr.Row(equal_height=True, elem_id="controller-header"):
            gr.HTML('<div class="brand"><span class="brand-dot"></span>Robot Zoo</div>', elem_id="controller-brand", min_width=150)
            robot = gr.Dropdown(
                choices=manager.robot_choices, value=initial_robot,
                show_label=False, container=False, interactive=True,
                scale=3, min_width=180,
            )
            load = gr.Button("Load", scale=0, min_width=64)
            pin = gr.Button("Pinned", visible=on_pin is not None, scale=0, min_width=76, elem_id="pin-control")
            pinned = gr.State(True)

        def toggle_pin(value):
            value = not value
            if on_pin is not None:
                on_pin(value)
            return value, "Pinned" if value else "Pin on top"

        pin.click(toggle_pin, inputs=pinned, outputs=(pinned, pin))

        assets = Path(__file__).parent

        def teleop(frame):
            # Gradio component server functions receive one JSON payload.
            try:
                if not isinstance(frame, list) or len(frame) != 5:
                    raise ValueError("Invalid joystick frame")
                return {"ok": True, "message": manager.teleop(*frame)}
            except (ValueError, RuntimeError, OSError) as exc:
                return {"ok": False, "message": str(exc)}

        pilot = gr.HTML(
            value=initial_robot,
            html_template=(assets / "joystick.html").read_text(),
            css_template=(assets / "joystick.css").read_text(),
            js_on_load=(assets / "input_mapping.js").read_text() + "\n" + (assets / "joystick.js").read_text(),
            server_functions=[teleop],
            elem_id="joystick-panel",
        )

        with gr.Row(equal_height=True, elem_id="footer-controls"):
            reset = gr.Button("Reset robot", scale=0, min_width=110)
        with gr.Accordion("More · actions & controls", open=False, elem_id="more-controls"):
            status = gr.Markdown(f"{initial_robot} ready.", elem_id="command-status")
            with gr.Row(visible=bool(initial_actions) and initial_robot != "Unitree Go2") as action_group:
                action = gr.Dropdown(
                    choices=initial_actions, value=initial_actions[0] if initial_actions else None,
                    label="Robot action", interactive=True, scale=3,
                )
                run_action = gr.Button("Run action", scale=1)
            gr.Markdown(
                "**Keyboard:** W/S forward/back · A/D strafe (Go2) or turn (TurtleBot3) · Q/E turn · R/F Go2 posture · Space stop.\n\n"
                "**Gamepad:** left stick moves, right stick turns only; its vertical axis is unused. "
                "D-pad moves slowly (left/right turns TurtleBot3). B stops. Go2: A stands, X lowers, Y raises. "
                "Enable the pad, center both sticks, and keep this window focused.\n\n"
                "**MuJoCo mouse:** double-click a body to select · "
                "Ctrl-drag to rotate · Ctrl-right-drag to move · F1 for help"
            )

        def action_update(selected_robot: str):
            choices = manager.actions_for(selected_robot)
            return gr.update(choices=choices, value=choices[0] if choices else None)

        def load_robot(selected_robot: str):
            message = manager.load_robot(selected_robot)
            return message, action_update(selected_robot), selected_robot, gr.update(visible=bool(manager.actions_for(selected_robot)) and selected_robot != "Unitree Go2")

        robot.change(action_update, inputs=robot, outputs=action)
        clear_input = "() => window.dispatchEvent(new Event('robot-zoo-reset-input'))"
        load.click(load_robot, inputs=robot, outputs=(status, action, pilot, action_group))
        load.click(None, js=clear_input, queue=False)
        run_action.click(manager.action, inputs=action, outputs=status)
        run_action.click(None, js=clear_input, queue=False)
        reset.click(manager.reset, outputs=status)
        reset.click(None, js=clear_input, queue=False)

    return demo


def launch_control_ui(
    manager: SimulationControls,
    *,
    inbrowser: bool = True,
    server_port: int | None = None,
    on_pin: Callable[[bool], None] | None = None,
) -> tuple[gr.Blocks, str]:
    demo = build_control_ui(manager, on_pin=on_pin)
    _, local_url, _ = demo.launch(
        inbrowser=inbrowser,
        prevent_thread_lock=True,
        server_name="127.0.0.1",
        server_port=server_port,
        share=False,
        quiet=True,
        show_error=True,
        footer_links=[],
        theme=gr.themes.Base(primary_hue="green", neutral_hue="slate"),
        css=CSS,
    )
    print(f"Gradio controller: {local_url}", flush=True)
    return demo, local_url
