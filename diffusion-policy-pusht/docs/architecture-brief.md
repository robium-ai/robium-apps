# Architecture brief — PushT with Diffusion Policy

## Objective

Provide a macOS-runnable PushT reference that starts from a successful
published Diffusion Policy, shows honest evidence, and lets visitors replay
randomized layouts live without first training a model.

## Stack

| Layer | Choice | Reason |
| --- | --- | --- |
| Dataset | `lerobot/pusht` | Canonical 206-episode PushT demonstrations and normalization statistics. |
| Policy | Pinned `lerobot/diffusion_pusht` 175k checkpoint | Published task-matched weights and 500-episode evaluation. |
| Runtime | LeRobot 0.6.0 | Current processor-aware policy interface. |
| Simulation | gym-pusht / pymunk | Matches the checkpoint's observation, action, and success contract. |
| Environment | uv, Python 3.12, native MPS | Reproducible lockfile and Apple GPU acceleration. |
| Demo | Gradio 6 + direct image + Rerun | Reliable primary RGB stream with an additive ML timeline. |

## Modules

```text
diffusion-policy-pusht/
├── src/diffusion_policy_pusht/
│   ├── config.py             # pinned IDs, modes, and optional research recipe
│   ├── official.py           # fetch, compatibility conversion, evidence manifest
│   ├── rollout.py            # checkpoint load and deterministic rollout
│   ├── ladder.py             # optional local-training evaluation
│   ├── shapes.py             # T benchmark and L/I/Z OOD geometries
│   ├── run.py                # CLI entry points
│   └── demo/
│       ├── episode_runner.py # lazy model cache, serialization, cancellation
│       ├── ui.py             # evidence workspace and live replay
│       └── app.py            # Gradio lifecycle / DEMO READY contract
├── tests/test_smoke.py       # official checkpoint + full MPS rollout
└── tests/test_demo.py        # real browser/API rollout smoke
```

`outputs/demo/ladder.json` is the generated contract between evidence and
UI. It records models, evidence kind, inference modes, and the default live
seed.

## Checkpoint adaptation

The official revision contains legacy normalization buffers inside the model
but no LeRobot 0.6 pre/postprocessor files. Preparation downloads the pinned
artifact, creates processors from the canonical dataset statistics, and
records that conversion in `robium-provenance.json`. It never changes
`model.safetensors`. Current LeRobot reports the legacy normalization
buffers as unexpected keys because normalization now belongs to the
processors; this is expected for this conversion.

## Demo behavior

The control rail selects policy evidence, inference mode, shape, and seed.
Fast mode uses 10 denoising passes; reference mode uses 100, matching the
published schedule. The main pane streams observations directly. Rerun logs
the same frame, action target, reward, and maximum coverage. L/I/Z remain
visibly labeled qualitative OOD probes.

The official 500-episode result and the interrupted local 5k experiment are
categorical evidence from different configurations, not a connected learning
curve. One process handles one rollout at a time; cancellation is checked at
each simulator step.

## Verification gates

1. `make check` validates local prerequisites.
2. `make prepare-official` proves the pinned artifact and processors exist.
3. `make smoke` checks provenance and completes a full real-policy episode.
4. `make demo-smoke` boots the app, streams direct RGB frames, completes T
   and L rollouts, verifies deterministic Z layouts, and exercises
   cancellation/lock release.
5. The published 65.4% result remains attributed to the official 500-episode,
   100-denoise evaluation. Fast-mode rollouts never inherit that metric.

## Known costs and limits

- Initial checkpoint download is roughly 1 GB; cached startup is local.
- Fast mode took about 21 seconds for 300 steps on the tested Apple M5.
  Reference mode is materially slower.
- Published evaluation used batched CUDA environments, so its per-episode
  timing is not comparable to sequential MPS demo timing.
- PushT is a 2D benchmark, not a real-robot transfer claim.
- No artifact upload or hosted deployment is authorized by this build.

Approved design and pivot:
`docs/superpowers/specs/2026-08-21-diffusion-policy-pusht-redesign.md`.
