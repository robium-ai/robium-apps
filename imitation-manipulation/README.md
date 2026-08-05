# imitation-manipulation

A robot learns to push a block by imitation — no reward engineering, no
GPU, no robot. An ACT policy is trained on human demonstrations of the
classic PushT task (push a gray T-block until it covers a green target
zone), then you watch it work — and fail — live in your browser: pick any
checkpoint from its training ladder, pick a block shape it has never seen,
and see exactly what the policy sees while it acts. Everything runs on a
laptop; the demo container is self-contained (pretrained checkpoints are
fetched from a public Hugging Face repo at build time).

**Stack:** LeRobot 0.6.0 · ACT · gym-pusht · Gradio + Rerun · uv · Docker

## What you'll see

- **The training ladder:** four checkpoints of the same recipe — 1k, 3k and
  5k steps frozen from one training run, plus a 10k-step baseline run — each
  labeled with its real evaluation numbers. Watch what more training buys,
  and what it doesn't: the ladder is honestly non-monotonic (the 5k rung
  out-evals the 10k baseline, 0.322 vs 0.310 avg_max_reward, in this
  build's 10-episode seeded evals).
- **Live episodes:** every control step streams onto an embedded Rerun
  timeline — the 96×96 frame the policy actually sees, its action commands,
  and the coverage reward. Scrub the timeline when the episode ends.
- **Generalization probes:** switch the block from the T it was trained on
  to an L, I or Z it has never seen, and watch how (whether) each checkpoint
  copes. Every run starts from a fresh random layout.
- **Honest numbers:** PushT counts "success" only at ≥95% target coverage,
  which ACT at this scale never reaches — `pc_success` is 0% at every rung.
  The max-coverage reward is the honest metric, and the Gallery tab shows
  each rung's real evaluation videos and metrics table.

## Prerequisites

- **Docker path (recommended):** just Docker. Works on any machine; the
  image fetches its checkpoints from the public Hub repo at build time.
- **Native path (Apple Silicon, faster inference via MPS):** [uv], Python
  3.12 (uv manages it), and one host dep: `brew install ffmpeg`.

[uv]: https://docs.astral.sh/uv/

## Quick start

```bash
make check                                             # preflight: deps + setup hints
make demo-image                                        # docker build (fetches checkpoints)
docker run --rm -p 8765:8765 imitation-manipulation:latest
# open http://localhost:8765 — wait for "DEMO READY" in the logs
```

Native (MPS) alternative:

```bash
uv sync
make fetch-artifacts   # pull the pretrained ladder from the Hub
make demo              # same app, MPS inference, http://localhost:8765
```

Nothing to train either way — the checkpoints, their eval metrics and the
gallery videos come from
[`robium/pusht-act-ladder`](https://huggingface.co/robium/pusht-act-ladder)
(no account or token needed).

## How it works

- **Task:** PushT (`gym-pusht`) — a 2D pymunk world; the agent is a circular
  end-effector, the action is a target xy position, the reward is how much
  of the green goal zone the block covers.
- **Policy:** ACT (Action Chunking with Transformers) trained with LeRobot
  on the `lerobot/pusht` demonstration dataset (206 human episodes). The
  policy is pixels-in, actions-out: it only ever sees the rendered frame.
- **Shape variants:** the demo registers a PushShape env whose block
  geometry is swapped by name (`src/imitation_manipulation/shapes.py`); the
  coverage metric and the goal silhouette derive from the block geometry,
  so L/I/Z episodes are scored exactly like T episodes. T is byte-identical
  to the training env; L/I/Z are out-of-distribution probes, not
  benchmarks.
- **The app is session-blind by design:** one process serves one demo and
  prints `DEMO READY` when checkpoints are loaded. Per-user isolation is
  the container boundary — an orchestrator (or a human with `docker run`)
  owns lifecycle; the app knows nothing about users.
- Architecture and design rationale: `docs/architecture-brief.md` (pipeline)
  and `docs/2026-08-03-public-demo-rescope-design.md` (demo); the story of
  the build: `docs/case-study.md`. Machine-readable contract:
  `robium-app.yaml` (reference-apps spec).

## Troubleshooting

- **`make demo` fails with `FileNotFoundError: … ladder.json`** — no demo
  artifacts yet. Run `make fetch-artifacts` (or train them; see below).
- **`make smoke` fails decoding the dataset** — ffmpeg is missing
  (`brew install ffmpeg`); torchcodec needs its shared libraries.
- **Port 8765 busy** — set `PORT`, e.g. `PORT=8770 make demo` (the
  container maps any host port: `-p 8770:8765`).
- **"MPS is not available. Switching to 'cpu'"** — expected inside the
  container and on non-Apple hosts; inference is slower but correct.
- **Two browser tabs, one app** — runs are serialized; a second Run waits
  up to 30 s for the first to finish, then errors. One episode at a time
  is by design (one container = one user).

## Cleanup

- `make clean` — delete `outputs/` (fetched or trained artifacts).
- `docker image rm imitation-manipulation:latest` — drop the demo image.
- `uv cache clean` / `rm -rf .venv` — reclaim the native environment.

## Reproduce the artifacts (maintainers)

The pipeline that produced the shipped checkpoints, all driven from
`src/imitation_manipulation/config.py` (single source of every run param):

| Command | What it does |
|---|---|
| `make smoke` | **The pass bar.** 200-step ACT train on MPS + 2-episode seeded eval, asserted via pytest (~40 s warm). |
| `make train-ladder` | 5k-step ACT run saving every 1k, pruned to rungs 1k/3k/5k (~8 min on M2 Pro MPS). |
| `make train-baseline` | 10k-step ACT train (~15 min on M2 Pro MPS) — the ladder's top rung. |
| `make eval-ladder` | 10-episode seeded eval of every rung → `outputs/demo/ladder.json` (the manifest the UI reads — generated, never hand-edited). |
| `make demo-smoke` | The demo ship bar: boot → `DEMO READY`, one T episode + one out-of-distribution L episode complete via the Gradio API. |
| `make upload-artifacts` | Publish `outputs/` artifacts to the Hub repo (maintainers, explicit approval only). |

Measured on an M2 Pro (2026-08-03): smoke test green post-rename (2 passed,
~40 s warm); ladder 5k train ≈ 10 min and baseline 10k train 21.4 min
(~7–8 steps/s on MPS); the full 4-rung, 10-episode-each seeded eval ≈ 2.5
min. Ladder `avg_max_reward`: 1k 0.182 · 3k 0.239 · 5k 0.322 · 10k 0.310 —
`pc_success` 0% at every rung, as expected at this scale.

## Gotchas encoded here (details: [robium](https://github.com/robium-ai/robium) learnings)

- `lerobot-eval` defaults to async vector envs whose forkserver workers
  never import `gym_pusht` → `NamespaceNotFound`/`BrokenPipeError`. All eval
  commands pass `--eval.use_async_envs=false`; the demo uses a single sync
  env by construction.
- No usable pretrained PushT baseline exists on the Hub for lerobot 0.6.0
  (the official `lerobot/diffusion_pusht` predates the processor-pipeline
  format and cannot load; the community-migrated copy evals at chance
  level). The shipped ladder is trained from scratch by this repo's own
  targets.
- lerobot's `viz` extra pins rerun-sdk <0.34, which conflicts with
  gradio_rerun 0.34.1 — this project pins `rerun-sdk==0.34.1` explicitly
  instead of using the extra.
- The demo Dockerfile's `pip install -e .` is load-bearing: `config.APP_ROOT`
  resolves from `config.py`'s `__file__`, so the module must live at
  `/app/src`, not in site-packages — or the fetched `outputs/` tree would
  never be found.
