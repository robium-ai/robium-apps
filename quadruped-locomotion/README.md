# go2-locomotion

Train a **Unitree Go2 quadruped to walk** with reinforcement learning in **NVIDIA
Isaac Lab** (rsl_rl PPO), on a **cloud NVIDIA GPU**. Produces a walking-Go2 video
plus a remote-GPU smoke test. Satisfies robium-applications issue #3 — "Demo:
Isaac Lab RL policy".

Full rationale, decisions, and phased plan: **[`docs/architecture-brief.md`](docs/architecture-brief.md)**.
The original scoping input is in [`HANDOFF.md`](HANDOFF.md).

## How it works (start here to understand the RL)

**→ [`docs/pipeline.md`](docs/pipeline.md)** — a plain-language walkthrough of the
training pipeline. The short version:

- **Trains from scratch** — random-weights neural net, no pretrained policy, no
  dataset. The Go2 learns to walk purely from a reward signal (this is *reinforcement*
  learning, unlike `vla-trial`'s fine-tuning).
- **Target:** velocity tracking on flat ground — follow a commanded base velocity
  with a stable gait (`Isaac-Velocity-Flat-Unitree-Go2-v0`).
- **Policy:** PPO (actor-critic) via `rsl_rl`; ~4096 Go2s train in parallel on the
  GPU, which is why a walking policy emerges in ~20–40 min.
- **How you watch it:** recorded MP4 clips per checkpoint (a flailing→walking
  progression) + TensorBoard reward curves — there's no local GUI (headless on the
  cloud pod). See pipeline.md §7.
- **Best read:** Rudin et al., ["Learning to Walk in Minutes"](https://arxiv.org/abs/2109.11978) — the paper behind this exact stack.

## The one thing that makes this app different

**Isaac Lab does not run on macOS / Apple Silicon — at all** (no NVIDIA GPU, no
CUDA). So unlike every other app in this repo, there is **no local mirror**: the
Mac is a thin SSH/browser client and *all* sim/training/smoke runs on a cloud GPU
pod. This deliberately breaks the repo's `local == remote reproduce` norm — a known
`environments`-skill gap, documented in the brief §1 and `learnings/`.

## Compute: RunPod (not GCP)

The GPU pod runs on **RunPod** — chosen over GCP because GCP's new-project GPU
quota gate is a 48h+ wall (we hit it) and a bad default for a reference app.
RunPod has no quota gate, boots the **official Isaac Sim container as the pod
image** (easiest Isaac Lab setup), and the whole job costs ~$2–6. See brief §3.

## Layout

```
src/go2_locomotion/
  config.py   # single source of truth: task id, run profiles, command builders
  run.py      # thin CLI over config's commands (runs ON the pod)
tests/
  test_config.py  # Mac-testable command-builder guards (the only no-GPU tests)
  test_smoke.py   # the pass bar — REMOTE-GPU, deselected off-pod (never fake-passes)
```

## Usage

**On the Mac (no GPU) — config guards only:**
```bash
make sync      # uv sync
make test      # pure-Python command-builder guards
```

**On the RunPod pod (Isaac Lab installed — see brief §3/§4):**
```bash
make list-envs   # SOURCE OF TRUTH for the task id — verify Go2 is listed first
make smoke       # the pass bar: SMOKE-profile train writes a checkpoint (mechanics)
make train-full  # the real ~20-40 min walking policy, with video
make play        # roll out the latest checkpoint -> walking-Go2 MP4
```

Override the pod's Isaac Lab location / python via `ISAACLAB_ROOT` and
`ISAACLAB_PYTHON` (see `config.py`).

## Results (2026-07-27) — ✅ walking policy trained + live demo

Verified end-to-end on a RunPod L4:

- **Walking policy trained from scratch** — 4096 envs · 2000 iters · **32 min** ·
  reward −0.5 → **+36**, never falls (episode length maxes at 1000). Policy exported
  to TorchScript + ONNX. Full detail: [`docs/architecture-brief.md`](docs/architecture-brief.md) §9.
- **Reward dashboard** (clickable checkpoint videos, iter 0 → 1999):
  <https://claude.ai/code/artifact/1661f6a2-c375-4975-9a90-0561517272d7>
- **Live control panel** — pilot the trained policy in the browser (velocity sliders
  + WASD/arrows + hot-swappable checkpoints), MJPEG-streamed: [`docs/live-demo.md`](docs/live-demo.md)
  + [`scripts/live_demo_patch.py`](scripts/live_demo_patch.py).
- **Artifacts** (checkpoints + exported policy + videos) saved to `outputs/` (git-ignored);
  pod terminated after capture.

**Reproduce:** stand up a RunPod L4 with the Isaac Sim NGC image (brief §3–4), then
`make list-envs` → `make train-full` → render/serve as in `docs/`. Mac-side `make
test` runs the pure-Python config guards; `make smoke` is the remote-GPU pass bar
(needs a pod). Next phases: rough terrain, then a GPU-backed live demo on robium.ai.
