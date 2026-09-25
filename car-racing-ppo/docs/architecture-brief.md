# Architecture brief: CarRacing PPO

**Date:** 2026-09-24
**Status:** canonical experimental reference application

## Outcome

Show a real pretrained vision policy driving a generated track locally on an
Apple Silicon Mac. The reference path opens a native simulation, uses the
published checkpoint without retraining, and records measured episode reward
and runtime speed.

## System boundary

```text
CarRacing 96x96 RGB observation
          |
          v
frame skip 2 -> resize 64 -> grayscale -> stack 2 frames
          |
          v
pinned Stable-Baselines3 PPO checkpoint on CPU
          |
          v
continuous steering + gas + brake
          |
          v
Gymnasium Box2D simulation + native Pygame window
```

## Decisions

| Decision | Choice | Reason |
| --- | --- | --- |
| Starting path | Small standalone reference app | No existing Robium automobile example matched; a robotics stack would add unrelated machinery |
| Policy | Published `pableitorr/ppo-CarRacing-v2` checkpoint unchanged | Fast visible proof with no training |
| Artifact | Pin repository revision and SHA-256 | Prevent silent checkpoint drift |
| Runtime | Host-native uv environment | Avoid Docker display and architecture friction |
| Versions | Python 3.10, SB3 2.3.2, Gymnasium 0.29.1 | Match the checkpoint's recorded training environment |
| Box2D build | Add SWIG to uv's isolated build dependencies | Apple Silicon has no `box2d-py` wheel; no manual Homebrew prerequisite |
| Inference | CPU | The policy is small enough for real-time native rendering |
| Evidence | Seeded headless episodes plus a visible seed-1 run | Separate measured local behavior from the model card's unverified score |

## Publication and license boundary

- Robium publishes the MIT-licensed runner, tests, documentation, and real-run
  screenshot, but no checkpoint bytes.
- The app downloads the external checkpoint by immutable revision and rejects
  any file whose SHA-256 differs.
- The upstream checkpoint repository declares no license. Every discovery
  surface identifies it as a third-party checkpoint with an unspecified
  license.
- Qualification is limited to Apple Silicon macOS. Other platforms remain
  unverified.
- Public wording identifies this as a toy visual-control benchmark, not a
  real-road autonomous-driving stack.

## Verified path

- A clean uv environment builds on Apple Silicon without manually installed
  SWIG.
- Seeds 0–2 produce distinct, reproducible tracks after the requested seed is
  reapplied following `PPO.load()`.
- Seed 1 completes the 275-tile lap with 912.50 reward.
- The native visible loop sustains approximately 47–48 FPS against the 50 FPS
  simulator render target on an Apple M5.

## Deferred

- Browser presentation and website hosting.
- Training or fine-tuning.
- Traffic, routes, language reasoning, trajectory prediction, and CARLA.
- Physical vehicle control.
- Linux and Intel macOS qualification.
