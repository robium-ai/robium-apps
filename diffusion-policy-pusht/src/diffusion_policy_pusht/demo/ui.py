"""Gradio workspace for checkpoint evidence and replayable live rollouts."""

from __future__ import annotations

import html
import math
import secrets
import uuid

import gradio as gr
import pandas as pd
import rerun as rr
import rerun.blueprint as rrb
from gradio_rerun import Rerun

from diffusion_policy_pusht import config

APP_ID = "diffusion_policy_pusht_demo"
THEME = gr.themes.Base(primary_hue="teal", neutral_hue="zinc")

CSS = """
:root { --dp-bg:#18181b; --dp-panel:#27272a; --dp-card:#27272a; --dp-line:#3f3f46;
  --dp-muted:#a1a1aa; --dp-accent:#2aa6aa; --dp-success:#4ade80; }
body, .gradio-container { background:var(--dp-bg) !important; color:#f4f4f5 !important; color-scheme:dark; }
.gradio-container {
  --body-background-fill:var(--dp-bg); --background-fill-primary:var(--dp-bg);
  --background-fill-secondary:var(--dp-panel); --block-background-fill:var(--dp-card);
  --block-border-color:var(--dp-line); --block-label-background-fill:var(--dp-card);
  --input-background-fill:var(--dp-bg); --input-border-color:var(--dp-line);
  --button-secondary-background-fill:var(--dp-card); --button-secondary-border-color:var(--dp-line);
  --button-secondary-text-color:#f4f4f5; --body-text-color:#f4f4f5;
  --body-text-color-subdued:var(--dp-muted); --block-label-text-color:var(--dp-muted);
  --block-title-text-color:#f4f4f5; --input-placeholder-color:var(--dp-muted);
  --checkbox-label-background-fill:var(--dp-card); --checkbox-label-background-fill-hover:#323238;
  --checkbox-label-background-fill-selected:#303a3a; --checkbox-label-border-color:var(--dp-line);
  --checkbox-label-border-color-hover:var(--dp-accent); --checkbox-label-border-color-selected:var(--dp-accent);
  --checkbox-label-border-width:1px; --checkbox-label-text-color:#f4f4f5;
  --checkbox-label-text-color-selected:#f4f4f5; --checkbox-background-color:var(--dp-bg);
  --checkbox-background-color-hover:var(--dp-bg); --checkbox-background-color-focus:var(--dp-bg);
  --checkbox-border-color:var(--dp-line); --checkbox-border-color-hover:var(--dp-accent);
  --checkbox-border-width:1px;
  max-width:none !important; padding:0 !important;
}
.gradio-container, .gradio-container * { font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
.dp-shell, .dp-shell .row, .dp-shell .column, .dp-shell .form { flex-wrap:nowrap !important; }
.dp-topbar { min-height:62px; display:flex; align-items:center; gap:14px; padding:8px 18px; color:#f4f4f5;
  border-bottom:1px solid var(--dp-line); background:var(--dp-bg); }
.dp-brand { font-size:23px; font-weight:700; line-height:1; letter-spacing:-.03em; }
.dp-title { color:#f7f8fa; font-weight:650; }
.dp-subtitle { color:var(--dp-muted); font-size:12px; margin-left:auto; }
.dp-dot { display:inline-block; width:9px; height:9px; margin-right:7px; border-radius:50%;
  background:var(--dp-success); box-shadow:0 0 0 4px rgba(74,222,128,.12); }
.dp-body { min-height:calc(100dvh - 62px); gap:0 !important; }
.dp-controls { min-width:270px; max-width:340px; padding:18px !important; border-right:1px solid var(--dp-line); background:var(--dp-panel); }
.dp-main { min-width:0; padding:18px !important; }
.dp-section { color:var(--dp-muted); font:600 11px/1.4 ui-monospace,monospace; letter-spacing:.1em; text-transform:uppercase; }
.dp-frame img { width:384px !important; height:384px !important; max-width:80% !important;
  max-height:90% !important; object-fit:contain !important; image-rendering:auto; background:#05070b; }
.dp-frame, .dp-frame > div { background:#05070b !important; }
.dp-controls label, .dp-controls input, .dp-controls textarea { color:#f4f4f5 !important; }
.dp-controls input { background:var(--dp-bg) !important; border-color:var(--dp-line) !important; }
.dp-result { border:1px solid var(--dp-line); border-radius:6px; padding:12px 14px; background:var(--dp-card); }
.dp-result strong { color:#fff; }
.dp-note { color:var(--dp-muted); font-size:12px; line-height:1.55; }
.dp-tabs { margin-top:10px; }
button.primary { background:var(--dp-accent) !important; border-color:var(--dp-accent) !important; }
.dp-controls button:not(.primary) { background:var(--dp-card) !important; border:1px solid var(--dp-line) !important; }
@media (max-width:820px) {
  .dp-body { flex-direction:column !important; }
  .dp-controls { min-width:0; max-width:none; border-right:0; border-bottom:1px solid var(--dp-line); }
  .dp-subtitle { display:none; }
}
"""


def _blueprint() -> rrb.Blueprint:
    return rrb.Blueprint(
        rrb.Horizontal(
            rrb.Spatial2DView(origin="sim", name="policy observation"),
            rrb.Vertical(
                rrb.TimeSeriesView(origin="coverage", name="coverage"),
                rrb.TimeSeriesView(origin="action", name="action target"),
            ),
            column_shares=[3, 2],
        ),
        collapse_panels=True,
    )


def _log_event(rec: rr.RecordingStream, event) -> None:
    rec.set_time("step", sequence=event.step)
    rec.log("sim", rr.Image(event.frame).compress(jpeg_quality=90))
    if not event.done:
        rec.log("reward/current", rr.Scalars([float(event.reward)]))
        rec.log("coverage/current", rr.Scalars([float(event.coverage)]))
    rec.log("coverage/max_so_far", rr.Scalars([float(event.max_coverage)]))
    if event.action is not None:
        rec.log("action/x", rr.Scalars([float(event.action[0])]))
        rec.log("action/y", rr.Scalars([float(event.action[1])]))


def _model_choices(manifest: dict) -> list[tuple[str, str]]:
    choices = []
    for model in manifest["models"]:
        evidence = model["evidence"]
        metrics = evidence["metrics"]
        suffix = "published" if evidence["kind"] == "published" else "local · partial"
        label = (
            f"{model['display_name']} · {metrics['success_rate']:.1%} success · "
            f"{metrics['avg_max_overlap']:.3f} overlap · {suffix}"
        )
        choices.append((label, model["name"]))
    return choices


def _evidence_frame(manifest: dict) -> pd.DataFrame:
    rows = []
    for model in manifest["models"]:
        metrics = model["evidence"]["metrics"]
        rows.extend(
            [
                {"model": model["display_name"], "metric": "success rate", "value": metrics["success_rate"]},
                {"model": model["display_name"], "metric": "avg max overlap", "value": metrics["avg_max_overlap"]},
            ]
        )
    return pd.DataFrame(rows)


def _evidence_table(manifest: dict) -> str:
    rows = [
        "| model evidence | source | episodes | success | avg max overlap |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for model in manifest["models"]:
        evidence = model["evidence"]
        m = evidence["metrics"]
        source = "published" if evidence["kind"] == "published" else "local partial"
        rows.append(
            f"| {model['display_name']} | {source} | {m['n_episodes']} | "
            f"{m['success_rate']:.1%} | {m['avg_max_overlap']:.3f} |"
        )
    rows.append("")
    rows.append(
        "These are not points on one learning curve: the local 5k experiment used a different "
        "configuration and its benchmark was stopped early. Official metrics come from the "
        "published 500-episode, 100-denoise evaluation. "
        f"Robium's aspirational release bar is {manifest['release_success_rate']:.0%} success."
    )
    return "\n".join(rows)


def _result_html(*, state: str, text: str, seed: int, shape: str) -> str:
    return (
        '<div class="dp-result">'
        f"<strong>{html.escape(state)}</strong><br>{html.escape(text)}<br>"
        f'<span class="dp-note">seed {seed} · shape {html.escape(shape)}</span>'
        "</div>"
    )


def build_ui(runner) -> gr.Blocks:
    manifest = runner.manifest
    default_seed = int(manifest["live_seed"])
    default_frame = runner.preview(config.DEMO_DEFAULT_SHAPE, default_seed)

    def resolve_seed(value: float | None) -> int:
        if value is None or not math.isfinite(float(value)):
            raise gr.Error("Enter a finite integer layout seed.")
        resolved = int(value)
        if resolved < 0:
            raise gr.Error("Layout seed must be zero or greater.")
        return resolved

    def preview(shape: str, seed: float):
        resolved = resolve_seed(seed)
        return runner.preview(shape, resolved), _result_html(
            state="Layout ready",
            text="Run this seed or change checkpoints while keeping the layout fixed.",
            seed=resolved,
            shape=shape,
        )

    def randomize(shape: str):
        seed = 20_000 + secrets.randbelow(2_000_000_000)
        return seed, *preview(shape, seed)

    def cancel():
        runner.cancel()
        return "Stopping after the current simulator step…"

    def run_episode(model: str, inference_mode: str, shape: str, seed: float):
        resolved = resolve_seed(seed)
        mode = manifest["inference_modes"][inference_mode]
        model_label = runner.models[model]["display_name"]
        rec = rr.RecordingStream(application_id=APP_ID, recording_id=str(uuid.uuid4()))
        stream = rec.binary_stream()
        rec.send_blueprint(_blueprint())
        status = f"Loading {model_label} · {mode['display_name']}…"
        yield runner.preview(shape, resolved), status, stream.read(), _result_html(
            state="Starting",
            text=f"{model_label} is preparing a {mode['display_name'].lower()} rollout.",
            seed=resolved,
            shape=shape,
        )
        print(
            f"[demo] run start model={model} mode={inference_mode} "
            f"shape={shape} seed={resolved}",
            flush=True,
        )
        try:
            for event in runner.run(
                model,
                inference_mode=inference_mode,
                shape=shape,
                seed=resolved,
            ):
                _log_event(rec, event)
                if event.done:
                    if event.aborted:
                        state = "Stopped"
                        text = f"Stopped after {event.step} steps; max coverage {event.max_coverage:.3f}."
                    elif event.success:
                        state = "Solved"
                        text = f"Reached ≥95% coverage in {event.step} steps."
                    else:
                        state = "Partial progress"
                        text = f"Max coverage {event.max_coverage:.3f}; success requires ≥0.95."
                    if shape != "T":
                        text += " This letter is an out-of-distribution probe, not a benchmark."
                    result = _result_html(state=state, text=text, seed=resolved, shape=shape)
                    status = f"{state.lower()} · step {event.step} · max coverage {event.max_coverage:.3f}"
                else:
                    result = _result_html(
                        state="Running",
                        text=f"Step {event.step}/{event.total}; max coverage {event.max_coverage:.3f}.",
                        seed=resolved,
                        shape=shape,
                    )
                    status = f"running · step {event.step}/{event.total} · max coverage {event.max_coverage:.3f}"
                yield event.frame, status, stream.read(), result
        except RuntimeError as exc:
            raise gr.Error(str(exc))

    with gr.Blocks(
        title="PushT with Diffusion Policy · Robium",
        elem_classes="dp-shell",
    ) as blocks:
        gr.HTML(
            '<header class="dp-topbar"><span class="dp-brand">robium</span>'
            '<span class="dp-title"><span class="dp-dot"></span>PushT with Diffusion Policy</span>'
            f'<span class="dp-subtitle">{runner.device.upper()} · official 175k policy · '
            f'fast + reference inference</span></header>'
        )
        with gr.Row(elem_classes="dp-body"):
            with gr.Column(scale=0, min_width=290, elem_classes="dp-controls"):
                gr.HTML('<div class="dp-section">Experiment controls</div>')
                model = gr.Radio(
                    choices=_model_choices(manifest),
                    value=runner.default_model,
                    label="Policy evidence",
                )
                inference_mode = gr.Radio(
                    choices=[
                        (value["display_name"], key)
                        for key, value in manifest["inference_modes"].items()
                    ],
                    value=runner.default_inference_mode,
                    label="Inference quality",
                )
                shape = gr.Radio(
                    choices=[
                        ("T · benchmark", "T"),
                        ("L · OOD", "L"),
                        ("I · OOD", "I"),
                        ("Z · OOD", "Z"),
                    ],
                    value=config.DEMO_DEFAULT_SHAPE,
                    label="Block shape",
                )
                seed = gr.Number(value=default_seed, precision=0, label="Layout seed")
                with gr.Row():
                    random_btn = gr.Button("Randomize layout")
                    replay_btn = gr.Button("Replay this seed")
                with gr.Row():
                    run_btn = gr.Button("Run rollout", variant="primary")
                    stop_btn = gr.Button("Stop")
                status = gr.Textbox(value="ready", label="Health", interactive=False)
                gr.Markdown(
                    "**T is the benchmark.** L/I/Z were never in training and are shown only as "
                    "out-of-distribution probes. PushT success means at least 95% target coverage. "
                    "Published 65.4% success applies only to the official 100-denoise evaluation."
                )
            with gr.Column(scale=1, elem_classes="dp-main"):
                frame = gr.Image(
                    value=default_frame,
                    label="Live policy observation · 96×96 pixels",
                    interactive=False,
                    height=520,
                    elem_classes="dp-frame",
                )
                result = gr.HTML(
                    _result_html(
                        state="Layout ready",
                        text="Choose a checkpoint or randomize the layout, then run.",
                        seed=default_seed,
                        shape=config.DEMO_DEFAULT_SHAPE,
                    )
                )
                with gr.Tabs(elem_classes="dp-tabs"):
                    with gr.Tab("Checkpoint evidence"):
                        gr.BarPlot(
                            value=_evidence_frame(manifest),
                            x="model",
                            y="value",
                            color="metric",
                            color_map={"success rate": "#4ade80", "avg max overlap": "#60a5fa"},
                            y_lim=[0, 1],
                            title="Published reference vs separate local experiment",
                            height=330,
                        )
                        gr.Markdown(_evidence_table(manifest))
                    with gr.Tab("Rerun timeline"):
                        viewer = Rerun(
                            streaming=True,
                            height=500,
                            panel_states={"time": "collapsed", "blueprint": "hidden", "selection": "hidden"},
                        )
                        gr.Markdown(
                            "The direct frame above is the primary live view. Rerun adds a scrub-able "
                            "image/action/reward timeline and is not required for the rollout to be visible."
                        )
                    with gr.Tab("Recorded same-seed rollouts"):
                        with gr.Row():
                            for model_info in manifest["models"]:
                                if not model_info["videos"]:
                                    continue
                                gr.Video(
                                    value=str(config.APP_ROOT / model_info["videos"][0]),
                                    label=model_info["display_name"],
                                    interactive=False,
                                )

        shape.change(preview, inputs=[shape, seed], outputs=[frame, result])
        seed.change(preview, inputs=[shape, seed], outputs=[frame, result])
        random_btn.click(randomize, inputs=[shape], outputs=[seed, frame, result])
        run_inputs = [model, inference_mode, shape, seed]
        run_outputs = [frame, status, viewer, result]
        run_btn.click(run_episode, inputs=run_inputs, outputs=run_outputs, api_name="run_episode")
        replay_btn.click(run_episode, inputs=run_inputs, outputs=run_outputs)
        stop_btn.click(cancel, outputs=[status], queue=False, api_name="cancel_episode")

    return blocks
