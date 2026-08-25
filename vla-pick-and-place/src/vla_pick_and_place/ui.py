"""Gradio proof workspace for a single protected rollout."""

from __future__ import annotations

import queue
import threading
from collections.abc import Iterator
from dataclasses import asdict

import gradio as gr

from vla_pick_and_place.config import CANONICAL_PROMPT, CURATED_STATES
from vla_pick_and_place.rollout import RolloutBusyError, RolloutEvent, RolloutRunner


def stream_rollout(
    runner: RolloutRunner, state_label: str, prompt: str
) -> Iterator[tuple[object, dict, object]]:
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
        {
            "phase": "starting",
            "message": "Starting the rollout. The first simulator frame can take a few seconds.",
        },
        gr.update(interactive=False),
    )
    while True:
        event = events.get()
        if event is None:
            break
        if isinstance(event, RolloutBusyError):
            yield (
                last_frame,
                {
                    "phase": "busy",
                    "message": "A rollout is already running. Wait for it to finish or cancel it, then retry.",
                },
                gr.update(interactive=False),
            )
            return
        if isinstance(event, BaseException):
            yield (
                last_frame,
                {
                    "phase": "failed",
                    "message": "The rollout failed. Retry after the session returns to ready.",
                },
                gr.update(interactive=True),
            )
            return
        if event.frame is not None:
            last_frame = event.frame
            yield (
                last_frame,
                {
                    "phase": event.phase,
                    "step": event.step,
                },
                gr.update(interactive=False),
            )
    result = asdict(result_box[0])
    result.pop("prompt", None)
    result.pop("action_latency_ms", None)
    yield last_frame, result, gr.update(interactive=True)


def build_ui(runner: RolloutRunner) -> gr.Blocks:
    def run_rollout(state_label: str, prompt: str):
        # This must itself be a generator function. Returning the generator
        # from a lambda makes Gradio treat it as one scalar output.
        yield from stream_rollout(runner, state_label, prompt)

    with gr.Blocks(title="Pi0.5 · LIBERO-Goal task 8") as blocks:
        gr.Markdown(
            "# Put the bowl on the plate\n"
            "One autonomous Franka Panda rollout. Success comes only from LIBERO's simulator."
        )
        with gr.Row():
            state = gr.Dropdown(
                choices=[item.label for item in CURATED_STATES],
                value=CURATED_STATES[0].label,
                label="Official fixed initial state",
            )
            prompt = gr.Textbox(
                value=CANONICAL_PROMPT, max_lines=2, label="Language instruction"
            )
        run = gr.Button("Run one rollout", variant="primary")
        cancel = gr.Button("Cancel")
        frame = gr.Image(label="Simulator frame", streaming=True)
        result = gr.JSON(label="Measured result")
        run.click(
            run_rollout,
            [state, prompt],
            [frame, result, run],
            api_name="run_rollout",
            trigger_mode="once",
        )
        cancel.click(runner.cancel, outputs=[], api_name="cancel_rollout")
    return blocks
