"""The demo's Gradio app: pick a rung on the training ladder and a block
shape -> Run -> embedded Rerun. Plus a Gallery tab with every rung's REAL
eval videos and metrics (from outputs/demo/ladder.json — generated, never
hand-edited).

Streaming pattern (fresh RecordingStream + recording_id per Run, yield
stream.read()) — same-id recordings MERGE in the viewer, so every Run mints
a new id.

Honesty is part of the layout: pc_success is 0% at every rung and the intro
says so — the ladder is NOT monotonic (the 5k rung out-evals the older 10k
baseline run) and the real numbers are shown per rung, noise and all. The
L/I/Z shapes are out-of-distribution probes the policy never saw in
training; they are labeled that way and never presented as benchmarks.
"""

import json
import uuid

import gradio as gr
import rerun as rr
import rerun.blueprint as rrb
from gradio_rerun import Rerun

from imitation_manipulation import config

APP_ID = "imitation_manipulation_demo"


def _manifest() -> dict:
    return json.loads(config.DEMO_LADDER_MANIFEST.read_text())


INTRO_MD = """\
**Pick a checkpoint from the training ladder, pick a block shape, hit Run.**
The ACT policy pushes the gray block toward the green target zone; every
control step streams onto the Rerun timeline below (the 96×96 frame the
policy sees, its actions, and the coverage reward) — scrub it when the
episode ends.

- The 1k/3k/5k rungs are one training run frozen at increasing steps; 10k is
  an earlier baseline run — **watch what more training buys (and what it
  doesn't: the ladder isn't monotonic, and the numbers shown are the real
  ones).**
- **Switch the block to L, I or Z — shapes the policy never saw in
  training — and watch how (whether) the checkpoints generalize.**
- PushT counts "success" only at ≥95% target coverage, which ACT at this
  scale never reaches — `pc_success` is 0% at every rung. The max-coverage
  reward is the honest metric.
"""

SHAPE_CHOICES = [
    ("T — the shape it was trained on", "T"),
    ("L — never seen in training", "L"),
    ("I — never seen in training", "I"),
    ("Z — never seen in training", "Z"),
]


def _blueprint() -> rrb.Blueprint:
    return rrb.Blueprint(
        rrb.Horizontal(
            rrb.Spatial2DView(origin="sim", name="what the policy sees"),
            rrb.Vertical(
                rrb.TimeSeriesView(origin="reward", name="coverage reward"),
                rrb.TimeSeriesView(origin="action", name="action (target xy)"),
            ),
            column_shares=[3, 2],
        ),
        collapse_panels=True,
    )


def _rung_choices(manifest: dict) -> list[tuple[str, str]]:
    return [
        (
            f"{r['name']} — {r['steps']:,} steps · avg_max_reward "
            f"{r['metrics']['avg_max_reward']:.3f} · {r['run']}",
            r["name"],
        )
        for r in manifest["rungs"]
    ]


def _gallery_md(manifest: dict) -> str:
    rows = [
        "| rung | steps | run | avg_max_reward | avg_sum_reward | pc_success |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in manifest["rungs"]:
        m = r["metrics"]
        rows.append(
            f"| {r['name']} | {r['steps']:,} | {r['run']} "
            f"| {m['avg_max_reward']:.3f} | {m['avg_sum_reward']:.1f} | {m['pc_success']:.0f}% |"
        )
    rows.append("")
    rows.append(
        f"Every row: a real {manifest['rungs'][0]['metrics']['n_episodes']}-episode "
        f"seeded eval (seed {manifest['seed']}) of that exact checkpoint, on the "
        "T block (the training distribution — OOD shapes are a live probe, not "
        "a benchmark)."
    )
    return "\n".join(rows)


def build_ui(runner) -> gr.Blocks:
    manifest = _manifest()

    def run_episode(rung: str, shape: str):
        # Fresh recording id per Run — same-id recordings MERGE in the viewer.
        rec = rr.RecordingStream(application_id=APP_ID, recording_id=str(uuid.uuid4()))
        stream = rec.binary_stream()
        rec.send_blueprint(_blueprint())
        yield stream.read(), f"resetting env — {rung} rung, {shape} block, episode starting…"

        print(f"[demo] run_episode start: rung={rung} shape={shape}", flush=True)
        ood = "out-of-distribution probe — " if shape != "T" else ""
        try:
            for ev in runner.run(rung, rec, shape=shape):
                if ev.step % 50 == 0 or ev.done:
                    print(f"[demo] step {ev.step} done={ev.done} success={ev.success}", flush=True)
                if ev.done:
                    if ev.success:
                        verdict = f"✅ ≥95% coverage — solved (max reward {ev.max_reward:.2f})"
                    else:
                        verdict = (
                            f"❌ no success — max coverage reward {ev.max_reward:.2f} "
                            "(success needs ≥95% coverage; expected at this training scale)"
                        )
                        if shape != "T":
                            verdict += " — the policy only ever saw the T"
                    yield stream.read(), f"finished at step {ev.step + 1}: {ood}{verdict}"
                else:
                    yield stream.read(), f"step {ev.step + 1}/{ev.total} · max reward {ev.max_reward:.2f}"
        except RuntimeError as e:  # run lock held — another episode is executing
            raise gr.Error(str(e))

    with gr.Blocks(title="imitation-manipulation — robium demo") as blocks:
        with gr.Tab("Run"):
            gr.Markdown(INTRO_MD)
            rung = gr.Radio(
                choices=_rung_choices(manifest),
                value=config.DEMO_DEFAULT_RUNG,
                label="checkpoint (the training ladder — real eval numbers, noise and all)",
            )
            shape = gr.Radio(
                choices=SHAPE_CHOICES,
                value=config.DEMO_DEFAULT_SHAPE,
                label="block shape (T = training distribution; the rest probe generalization)",
            )
            run_btn = gr.Button("Run episode (fresh random start each run)", variant="primary")
            status = gr.Textbox(value="idle", label="status", interactive=False)
            viewer = Rerun(
                streaming=True,
                height=560,
                panel_states={"time": "collapsed", "blueprint": "hidden", "selection": "hidden"},
            )
            run_btn.click(
                run_episode, inputs=[rung, shape], outputs=[viewer, status], api_name="run_episode"
            )

        with gr.Tab("Gallery — the ladder, evaluated"):
            gr.Markdown(_gallery_md(manifest))
            with gr.Row():
                for r in manifest["rungs"]:
                    video = config.APP_ROOT / r["videos"][0]
                    gr.Video(
                        value=str(video),
                        label=f"{r['name']} ({r['steps']:,} steps) — eval episode 0",
                        interactive=False,
                    )

    return blocks
