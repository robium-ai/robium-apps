"""Compact Gradio workspace for one protected Pi0.5 task."""

from __future__ import annotations

import queue
import threading
from collections.abc import Iterator

import gradio as gr

from vla_pick_and_place.config import CANONICAL_PROMPT, CURATED_STATES
from vla_pick_and_place.rollout import RolloutBusyError, RolloutEvent, RolloutRunner


CSS = """
:root { --pi-bg:#18181b; --pi-panel:#27272a; --pi-line:#3f3f46; --pi-muted:#a1a1aa; --pi-blue:#2563eb; }
html, body { width:100%; height:100%; margin:0; overflow:hidden !important; }
body, .gradio-container { background:var(--pi-bg) !important; color:#f4f4f5 !important; color-scheme:dark; }
.gradio-container { --body-background-fill:var(--pi-bg); --background-fill-primary:var(--pi-bg);
  --background-fill-secondary:var(--pi-panel); --block-background-fill:var(--pi-panel);
  --block-border-color:var(--pi-line); --block-label-background-fill:var(--pi-panel);
  --input-background-fill:var(--pi-bg); --input-border-color:var(--pi-line);
  --button-secondary-background-fill:var(--pi-panel); --button-secondary-border-color:var(--pi-line);
  --button-secondary-text-color:#f4f4f5; --body-text-color:#f4f4f5;
  --body-text-color-subdued:var(--pi-muted); --block-label-text-color:var(--pi-muted);
  --block-title-text-color:#f4f4f5; width:100% !important; height:100dvh !important; max-width:none !important; padding:0 !important;
  overflow:hidden !important; }
.gradio-container > main { max-width:none !important; margin:0 !important; padding:0 !important; }
.gradio-container footer { display:none !important; }
.gradio-container, .gradio-container * { font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
.pi-body { height:100dvh; min-height:0 !important; gap:0 !important; flex-wrap:nowrap !important; overflow:hidden; }
.pi-controls { min-width:280px !important; max-width:340px !important; height:100%; padding:18px !important;
  gap:12px !important; flex-direction:column !important; flex-wrap:nowrap !important; overflow:hidden;
  border-right:1px solid var(--pi-line); background:var(--pi-panel); }
.pi-controls > * { flex-shrink:0 !important; }
.pi-controls label, .pi-controls input, .pi-controls textarea { color:#f4f4f5 !important; }
.pi-controls input, .pi-controls textarea { background:var(--pi-bg) !important; border-color:var(--pi-line) !important; }
.pi-controls button { min-height:44px !important; }
.pi-controls button.primary { background:var(--pi-blue) !important; border-color:var(--pi-blue) !important; }
.pi-controls .secondary { background:var(--pi-panel) !important; border:1px solid var(--pi-line) !important; color:#f4f4f5 !important; }
.pi-status { margin-top:auto !important; }
.pi-status textarea { resize:none !important; }
.pi-stage { min-width:0 !important; max-width:none !important; height:100%; min-height:0 !important;
  padding:18px !important; gap:0 !important; overflow:hidden; background:#05070b; }
.pi-camera-title { flex:0 0 auto !important; margin:0 !important; padding:7px 10px !important;
  border:1px solid var(--pi-line); border-bottom:0; border-radius:4px 4px 0 0; background:var(--pi-panel); color:var(--pi-muted); }
.pi-camera-title p { margin:0 !important; font-size:12px !important; }
.pi-frame { flex:1 1 auto !important; min-width:0 !important; min-height:0 !important; margin:0 !important;
  padding:0 !important; border:1px solid var(--pi-line) !important; border-radius:0 0 4px 4px !important;
  overflow:hidden !important; background:#05070b !important; }
.pi-frame > div, .pi-frame .image-container, .pi-frame .wrap { width:100% !important; height:100% !important;
  min-height:0 !important; background:#05070b !important; }
.pi-frame img { width:100% !important; height:100% !important; object-fit:contain !important; background:#05070b !important; }
.pi-frame [data-testid="status-tracker"] { display:none !important; }
@media (max-width:680px) {
  html, body, .gradio-container { height:auto !important; min-height:100%; overflow:auto !important; }
  .pi-body { height:auto; min-height:100dvh !important; flex-direction:column !important; overflow:visible; }
  .pi-controls { min-width:0 !important; max-width:none !important; width:100% !important; height:auto; border-right:0; border-bottom:1px solid var(--pi-line); }
  .pi-status { margin-top:0 !important; }
  .pi-stage { width:100% !important; height:58vh; min-height:420px !important; }
}
"""


def stream_rollout(
    runner: RolloutRunner, state_label: str, prompt: str
) -> Iterator[tuple[object, str, object]]:
    state_id = next(
        state.state_id for state in CURATED_STATES if state.label == state_label
    )
    events: queue.Queue[RolloutEvent | BaseException | None] = queue.Queue()
    result_box = []

    def run() -> None:
        try:
            result_box.append(runner.run(state_id, prompt, events.put))
        except Exception as error:  # noqa: BLE001 - surfaced in the UI, not silently logged
            events.put(error)
        finally:
            events.put(None)

    threading.Thread(target=run, daemon=True).start()
    last_frame = None
    yield (
        None,
        "Getting the robot ready…",
        gr.update(interactive=False),
    )
    while True:
        event = events.get()
        if event is None:
            break
        if isinstance(event, RolloutBusyError):
            yield (
                last_frame,
                "Another task is already running. Stop it or wait, then try again.",
                gr.update(interactive=False),
            )
            return
        if isinstance(event, BaseException):
            yield (
                last_frame,
                "Something went wrong. Please try again.",
                gr.update(interactive=True),
            )
            return
        if event.frame is not None:
            last_frame = event.frame
            yield (
                last_frame,
                f"Working… step {event.step}",
                gr.update(interactive=False),
            )
    status = (
        "Done — the bowl is on the plate."
        if result_box[0].success
        else "Done — the bowl did not reach the plate."
    )
    yield last_frame, status, gr.update(interactive=True)


def build_ui(runner: RolloutRunner) -> gr.Blocks:
    def run_rollout(state_label: str, prompt: str):
        # This must itself be a generator function. Returning the generator
        # from a lambda makes Gradio treat it as one scalar output.
        yield from stream_rollout(runner, state_label, prompt)

    theme = gr.themes.Base(primary_hue="blue", neutral_hue="zinc")
    with gr.Blocks(title="Pi0.5 · Put the bowl on the plate", theme=theme, css=CSS) as blocks:
        with gr.Row(elem_classes="pi-body"):
            with gr.Column(scale=0, min_width=280, elem_classes="pi-controls"):
                state = gr.Dropdown(
                    choices=[
                        (f"Initial state {index + 1}", item.label)
                        for index, item in enumerate(CURATED_STATES)
                    ],
                    value=CURATED_STATES[0].label,
                    label="Initial state",
                )
                prompt = gr.Textbox(
                    value=CANONICAL_PROMPT,
                    lines=3,
                    max_lines=3,
                    label="Instruction",
                )
                run = gr.Button("Run task", variant="primary")
                cancel = gr.Button("Stop", variant="secondary")
                status = gr.Textbox(
                    value="Ready",
                    label="Status",
                    lines=2,
                    max_lines=2,
                    interactive=False,
                    elem_classes="pi-status",
                )
            with gr.Column(scale=1, elem_classes="pi-stage"):
                gr.Markdown("Pi0.5 simulator", elem_classes="pi-camera-title")
                frame = gr.Image(
                    show_label=False,
                    container=False,
                    streaming=True,
                    interactive=False,
                    elem_classes="pi-frame",
                )
        run.click(
            run_rollout,
            [state, prompt],
            [frame, status, run],
            api_name="run_rollout",
            trigger_mode="once",
        )
        cancel.click(runner.cancel, outputs=[], api_name="cancel_rollout")
    return blocks
