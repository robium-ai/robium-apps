# Architecture brief — PushT with Diffusion Policy

## Objective

Provide a macOS-runnable PushT reference that starts from a successful
published Diffusion Policy, shows honest evidence, and lets visitors replay
randomized layouts live without first training a model.

## Stack

| Layer | Choice | Reason |
| --- | --- | --- |
| Dataset | `lerobot/pusht` | Canonical 206-episode PushT demonstrations. |
| Policy | Pinned `lerobot/diffusion_pusht` 175k checkpoint | Published task-matched weights and 500-episode evaluation. |
| Runtime | LeRobot 0.6.0 | Current processor-aware policy interface. |
| Simulation | gym-pusht / pymunk | Matches the checkpoint's observation, action, and success contract. |
| Environment | uv, Python 3.12, native MPS + Linux CPU image | One lock with platform-specific PyTorch sources. |
| Demo | Gradio 6 + direct image + Rerun | Reliable primary RGB stream with an additive ML timeline. |
| Gateway | FastAPI + uvicorn | Website-compatible claims, readiness, expiry, and `/ui` mount. |

## Modules

```text
diffusion-policy-pusht/
├── app                         # shared doctor/build/run/status/logs/stop interface
├── src/diffusion_policy_pusht/
│   ├── config.py             # pinned IDs, modes, and optional research recipe
│   ├── official.py           # fetch, compatibility conversion, evidence manifest
│   ├── rollout.py            # checkpoint load and deterministic rollout
│   ├── ladder.py             # optional local-training evaluation
│   ├── shapes.py             # generalized L/I/Z OOD geometries
│   ├── run.py                # CLI entry points
│   └── demo/
│       ├── episode_runner.py # lazy model cache, serialization, cancellation
│       ├── ui.py             # evidence workspace and live replay
│       ├── app.py            # native Gradio entry point
│       └── gateway.py        # session lifecycle + mounted Gradio `/ui`
├── docker/demo.Dockerfile    # offline-at-runtime CPU demo image
├── scripts/demo_container_smoke.py
├── tests/test_app_cli.sh     # launcher contract and lifecycle
├── tests/test_smoke.py       # official checkpoint + full MPS rollout
└── tests/test_demo.py        # real browser/API rollout smoke
```

`outputs/demo/ladder.json` is the generated contract between evidence and
UI. It records models, evidence kind, inference modes, and the default live
seed.

## Checkpoint adaptation

The official revision contains legacy normalization buffers inside the model
but no LeRobot 0.6 pre/postprocessor files. Preparation downloads the pinned
artifact, reads the exact image/state/action normalization buffers from
`model.safetensors`, and transplants them into current processor files. It
records that conversion in `robium-provenance.json` and never changes the
weights. The embedded image mean/std are ImageNet statistics, not the current
dataset pixel statistics, so the smoke test checks them tensor-for-tensor.

## Demo behavior

The control rail selects policy evidence, inference mode, shape, and seed.
Fast mode uses 10 denoising passes; reference mode uses 100, matching the
published schedule. The main pane streams observations directly. Rerun logs
the same frame, action target, reward, and maximum coverage. L/I/Z remain
visibly labeled qualitative OOD probes. T uses the untouched upstream
environment, including its historical compound-body inertia; the generalized
letter builder is never used for benchmark runs.

The hosted entry point answers status immediately and loads the policy on a
background thread. `DEMO READY` is emitted only after the real checkpoint and
environment load. The image bakes the pinned Hub snapshot and compatibility
processors, sets `HF_HUB_OFFLINE=1`, and uses CPU-only Linux torch wheels.

The official 500-episode result and the interrupted local 5k experiment are
categorical evidence from different configurations, not a connected learning
curve. One process handles one rollout at a time; cancellation is checked at
each simulator step.

## Verification gates

1. `./app doctor` validates local prerequisites without changing the system.
2. `./app build` prepares the locked environment, pinned artifact, and processors.
3. `tests/test_app_cli.sh` verifies the shared six-command launcher and its
   run/status/stop lifecycle without loading the real model.
4. `make smoke` checks the launcher, provenance, and a full real-policy episode.
5. `make demo-smoke` boots the app, streams direct RGB frames, completes T
   and L rollouts, verifies deterministic Z layouts, and exercises
   cancellation/lock release.
6. `make demo-container-smoke` verifies the baked CPU image, claim guards,
   mounted UI, and a real seed-1000 rollout through the hosted API.
7. The published 65.4% result remains attributed to the official 500-episode,
   100-denoise evaluation over seeds 1000–1499. Fast-mode rollouts never
   inherit that metric.

## Known costs and limits

- Initial checkpoint download is roughly 1 GB; cached startup is local.
- Fast mode took about 21 seconds for 300 steps on the tested Apple M5.
  A corrected reference run solved official seed 1000 in 231 steps and 164
  seconds with 0.955 maximum raw coverage.
- Published evaluation used batched CUDA environments, so its per-episode
  timing is not comparable to sequential MPS demo timing. MPS and CUDA
  stochastic rollouts should be compared statistically, not bit-for-bit.
- PushT is a 2D benchmark, not a real-robot transfer claim.
- The local CPU image solved official seed 1000 in 116 steps at 0.953 raw
  coverage during the hosted lifecycle smoke.
- No artifact upload or production deployment was performed by this build.

Approved design and pivot:
`docs/superpowers/specs/2026-08-21-diffusion-policy-pusht-redesign.md`.
