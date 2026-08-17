# vla-pick-and-place

Tell a robot what to do in plain English, and watch it try. You type an
instruction ("put the green cube in the bin"), and a vision-language-action
(VLA) model — a neural network that maps camera images plus your sentence
directly to joint motions — drives a simulated SO-101 robot arm in MuJoCo
physics. Everything except GPU training runs natively on a laptop: the
simulation, the scripted expert that generates demonstrations, policy
evaluation, and a browser demo. Fine-tuning happens on a rented cloud GPU
(Hugging Face Jobs) because a laptop is orders of magnitude too slow for it.

**Current state:** the scripted controller completes the task, and the full
record → train → evaluate pipeline is working. The included SmolVLA
checkpoint has 100 training steps and currently scores 0/10 evaluation
episodes. A longer training run is still needed before the learned policy can
complete the task reliably.

**Stack:** SmolVLA 450M · LeRobot 0.6.0 · MuJoCo 3.10 (SO-101 arm) ·
uv + Python 3.12 (Apple Silicon MPS) · HF Jobs (GPU training) · Rerun ·
Gradio

## What you'll see

- **The oracle:** a hand-written inverse-kinematics controller picks the cube
  and drops it in the bin using ground-truth state — real physics, no
  learning. 10/10 on its tuned seeds; the day-1 canary for the whole scene.
- **The data engine:** the oracle replayed 75× with randomized cube spawns,
  recorded as a LeRobot dataset (failed episodes discarded and re-rolled).
- **The training loop:** the dataset pushed to the Hub, SmolVLA fine-tuned on
  a cloud GPU, the checkpoint pulled back and scored in sim.
- **The demo page:** a Robium workspace with an embedded Rerun viewer. It opens
  on a real reset frame, then streams cameras, joints, and actions while the
  selected controller runs.

## Prerequisites

- macOS on Apple Silicon (uses MPS for inference; `MUJOCO_GL=cgl` required
  for headless rendering) or Linux (`MUJOCO_GL=egl`). No GPU needed locally.
- [uv](https://docs.astral.sh/uv/) — the only environment tool used.
- A Hugging Face account for the Hub-backed stages (dataset push, GPU
  training, the demo's trained checkpoint). The dataset/checkpoint repos are
  private; `HF_USER` (default `robium`) selects the Hub namespace, and HF
  Jobs training needs prepaid credits on top of `hf auth login`.
- Docker, only for the demo container (`make demo-image`).

## Quick start

```bash
./app doctor   # prerequisites, assets, port, Hub auth
./app run      # install if needed, then serve the demo UI on :8765
```

`./app` sets `MUJOCO_GL` for you (`cgl` on macOS, `egl` on Linux) — it is not
optional and not auto-detected, and getting it wrong is a hang rather than an
error. The other verbs:

```bash
./app oracle           # scripted IK pick, 10 episodes — the "is it alive" canary
./app eval [CKPT]      # roll a checkpoint out in sim and score it
./app test             # the regression suite (no Hub access needed)
./app help
```

The `make` targets underneath remain the full surface (recording, training,
container builds) — see the pipeline table below. Training your own policy:
**[docs/training-guide.md](training-guide.md)**.

The app's machine-readable contract is `robium-app.yaml` (reference-apps
spec v1): standard verbs (`build`/`demo`/`smoke`/`check`/`test`) and the
mode list. It declares `hosted: false` — the demo runs on your machine, not
on hosted infrastructure.

`make oracle` is the fastest real signal in this repo: if it ever drops below
10/10 on seeds 0-9, something in the scene/physics/success-predicate broke,
independent of any policy question.

The pass bar, `make smoke`, evaluates a checkpoint in sim end-to-end. It
needs the local 5-step smoke checkpoint to exist first:

```bash
make train-smoke   # ~2 min on CPU: proves the training loop assembles and
                   # writes the local smoke checkpoint make smoke evaluates.
                   # Needs Hub access (base model + your dataset).
make smoke         # eval pipeline end-to-end on that checkpoint
```

## The full pipeline

Each stage is a `Makefile` target wrapping `python -m vla_pick_and_place.run <cmd>`;
`src/vla_pick_and_place/config.py` is the single source of truth for every
run parameter (steps, batch size, paths, seeds) — the Makefile and the tests
both build their invocations from it, so a hand-run stage and the pass-bar
test can never drift apart.

| Stage | Command | What it does |
| --- | --- | --- |
| Oracle canary | `make oracle` | scripted IK picks + drops, 10 episodes, ground-truth state — the smoke test for the *scene*, not the policy |
| Visual spot-check | `make viz-oracle` | one oracle episode logged to Rerun (`outputs/viz/oracle.rrd`) |
| Record | `make record` | run the oracle 75x, discard/retry episodes it fails, save a `LeRobotDataset` locally (no Hub push) |
| Push | `make push-dataset` | push the reviewed local dataset to the Hub (private) — a separate, deliberate step from `record` |
| Train (pipe-test) | `make train` | submit a cheap, deliberately under-trained fine-tune to HF Jobs (100 steps, a10g-small, ~$1-2) — proves the remote loop, not a real policy |
| Train (real) | `make train-full` | the actual 20k-step fine-tune (~4h on an A100-class GPU, ~$20-40) — **not yet run** |
| Eval | `make eval CKPT=<repo_id_or_path>` | roll a checkpoint out in sim, N seeded episodes, write `outputs/eval/*/eval_info.json` with a numeric success rate |
| Pipe-test pass bar | `make smoke` | asserts the eval PIPELINE runs end-to-end on the local 5-step checkpoint (loads, rolls out, writes JSON) — NOT a `>=60%` score bar |
| Narrative harness | `MUJOCO_GL=cgl uv run pytest tests/test_narrative.py -m slow` | asserts the base-vs-fine-tuned COMPARISON MACHINERY works (two checkpoints, two distinct output dirs, both produce numeric rates) — not the demo's eventual claim; see the file's `TODO(full-training)` |
| Demo (native, MPS) | `./app run` / `make demo` | the demo-page gateway on :8765 — FastAPI session contract + Gradio/`gradio_rerun` UI (`src/vla_pick_and_place/demo/`) |
| Demo (container) | `make demo-image` | build `vla-pick-and-place:latest` (CPU/osmesa; checkpoint baked in via a BuildKit HF-token secret) — what the website's orchestrator spawns |
| Demo pass bar | `make demo-smoke` | boots the real gateway: DEMO READY, session guards (409/403), one oracle episode succeeds THROUGH the Gradio API, /shutdown exits |

There is a free, local, CPU-only gate in front of every paid step:
`train-smoke` (a handful of CPU steps, ~2 min, catches config/shape errors)
must pass before `make train` ever touches HF Jobs money. This caught a real
bug for free once already (see Hard-won facts).

## Checkpoint status

**Available now:**
- The scene, IK, and success predicate are correct: the oracle picks and
  releases the cube into the bin 10/10 on tuned seeds using real MuJoCo
  physics, not a scripted animation.
- The dataset is real: 75 clean episodes (9 discarded for oracle misses),
  recorded with real physics and pushed to the Hub.
- The **entire remote training loop** is real and has run to completion on
  GPU: submit to HF Jobs -> train -> save checkpoint -> push to Hub -> pull
  -> eval in sim. The 100-step checkpoint the demo's "trained" controller
  loads (`robium-admin/train_2026-07-15_08-09-36`) is a genuine artifact of
  that loop, not a placeholder — re-verified 2026-08-17: it loads, rolls out
  10 episodes, and scores 0%.
- The eval pipeline is real: camera renaming, action un-normalization, and
  the sim rollout loop are all exercised against a real trained checkpoint,
  not mocked.

**Still to train:**
- **No checkpoint has been trained long enough to succeed.** The pipe-test
  checkpoint is 100 steps (a10g-small, ~$1-2) — essentially the base model —
  and scores 0/10 = 0%. The next model run is `make train-full` (20k steps,
  ~$20-40; reference success rate 60-80%).
- The narrative test (`tests/test_narrative.py`) proves the comparison
  *harness* works, not the demo's eventual "base flails, fine-tuned clears
  60%" claim — that assertion is commented out with a grep-able
  `TODO(full-training)` until a real 20k-step checkpoint exists.

## Hard-won facts (read before you touch this app)

- **macOS MuJoCo GL contexts (CGL) are thread-affine — cross-thread rendering
  is a silent DEADLOCK, not an error.** A renderer created on one thread hangs
  forever in cgl `make_current` when another thread renders with it; any
  thread pool (Gradio handlers, ThreadPoolExecutor) triggers this even though
  "it worked at boot". The demo constructs a fresh env per run in the running
  thread (see `src/vla_pick_and_place/demo/episode_runner.py`'s docstring).
- **Never train on macOS.** MPS fine-tuning is ~2 hours per 20 steps — CPU is
  even worse. All training happens on HF Jobs (remote GPU); local MPS is for
  *inference/eval only*, where SmolVLA is fast (~0.55 s/forward-pass on
  Apple Silicon, ~17x faster than CPU on the same machine — see the M0 spike
  in `docs/architecture-brief.md`).
- **The pedestal + wrist-roll grasp is a matched, load-bearing pair.** The
  cube sits on a 0.06 m pedestal (`scene_pick.xml`) — without it, the arm's
  reach geometry forces a downward finger pitch that makes grasping
  structurally impossible, independent of any IK tuning. On top of that,
  *position-only IK leaves the wrist roll free*, and a free roll can leave
  the gripper's pinch axis vertical (trying to span the cube's 6cm height
  with a 4.2cm aperture) instead of horizontal (spanning its 4cm width).
  Both the pedestal height (0.06) and the grasp offset
  (`ORACLE_GRASP_LOCAL` in `config.py`) were swept end-to-end together — do
  not change one without re-sweeping the other.
- **Camera renaming is required at both train AND eval.** SmolVLA's base
  checkpoint expects exactly three cameras named `observation.images.camera1/
  2/3`; our env has two (`wrist`, `scene`). Fix:
  `--rename_map={"observation.images.wrist":"observation.images.camera1",
  "observation.images.scene":"observation.images.camera2"}` plus
  `--policy.empty_cameras=1` for a masked placeholder covering the missing
  third camera. The fine-tuned checkpoint's own saved
  `policy_preprocessor.json` bakes this rename in — at eval time you feed
  the env's raw `wrist`/`scene` keys and the checkpoint renames them
  internally; renaming yourself first would break it (see
  `src/vla_pick_and_place/policy/evaluate.py`'s module docstring).
- **LeRobot's default video encoder (SVT-AV1) intermittently crashes at
  teardown on macOS**, killing a dataset-recording run as
  `BrokenProcessPool` (SIGTRAP in `svt_destroy_semaphore` — a libdispatch
  dispose-while-busy race; a 75-episode recording died at episode 60 this
  way). `record()` therefore passes `vcodec="auto"` (`RECORD_VCODEC` in
  `config.py`), which uses the hardware VideoToolbox encoder on macOS and
  only falls back to SVT-AV1 where no hardware encoder exists.
- **Remote `--output_dir` must be a container path, never a local Mac
  path.** `--output_dir` is passed verbatim to the HF Jobs container. A
  local absolute path trains to completion and then crashes at checkpoint
  save with `PermissionError: '/Users'` — a full paid run for zero artifact.
  `REMOTE_OUTPUT_DIR` in `config.py` is a `/tmp/...` container path for
  exactly this reason.
- **HF Jobs needs prepaid credits, separately from being logged in**, and a
  correctly-formed submission fails with `402 Payment Required` if the
  account has none — a safe, free way to validate the whole submission
  (auth, dataset, command shape) before adding credits.
- **HF Jobs ignores `--policy.repo_id` for the final push.** The trained
  model lands at an auto-generated `<user>/train_<timestamp>` repo instead —
  you have to read the "Model pushed to `<url>`" line in the job log to find
  the real checkpoint; you cannot assume it landed where you asked.

## Full docs

- `docs/training-guide.md` — how to train a policy that actually clears the
  bar, in order, with the traps that cost real money called out.
- `docs/architecture-brief.md` — stack rationale, M0 spike results
  (render throughput + SmolVLA latency), pipe-test results, and the full
  `Battle scars` section.
- `../REGISTRY.md` — this app's registry card (bootstrap-for list,
  battle scars index).
- `learnings/2026-07-14-vla-trial.md` and `learnings/2026-07-15-vla-trial.md`
  in the [robium](https://github.com/robium-ai/robium) repo — the
  session-by-session friction log this README and the brief are distilled
  from (dated files keep the app's pre-rename name, `vla-trial`).
