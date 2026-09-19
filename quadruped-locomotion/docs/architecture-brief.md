# Architecture Brief: Quadruped locomotion

**Date:** 2026-08-28
**Status:** active

## Goal and constraints

Publish a reference application that shows a Unitree Go2 learning to follow
velocity commands in Isaac Lab. The primary demo should let visitors move the
robot in a live simulator and switch checkpoints to compare policy behavior.
Recorded checkpoints remain durable evidence when hosted capacity is paused.

Isaac Lab does not run on the development Mac, so real simulation, smoke,
training, and live validation happen on a compatible remote NVIDIA GPU. Paid
allocation, artifact publication, and deployment are separate approval points.

## Decisions

| Decision | Choice | Why now | Confidence |
|---|---|---|---|
| First working slice | Live controller backed by the recovered run, with recorded clips retained as evidence | Lets visitors feel the policy difference directly while preserving a no-GPU fallback | validated |
| Training path | Existing Isaac Lab Go2 velocity task with RSL-RL | It produced the recovered walking policy and remains the shortest route to the requested result | validated |
| Environment | Thin local Python wrapper plus an installed Isaac Lab GPU environment | Local code stays testable while simulator ownership remains upstream | validated |
| Live experience | Capability-scoped MJPEG viewport, velocity/keyboard control, reset, and checkpoint hot-swap behind the shared RunPod lifecycle | This exact control seam passed a GPU-host smoke and avoids the Isaac editor/policy stepping conflict | validated |
| Artifact home | Hugging Face evidence repository | Keeps large checkpoints and videos outside Git with an immutable revision | provisional until publication |

## Provisional assumptions and risks

| Assumption or risk | Impact | Cheapest validation | Authorized pivot |
|---|---|---|---|
| The installed Isaac Lab still registers the Go2 flat task | Training cannot start if the task moved | Run `make list-envs` on the GPU host | Update the task name or nearby supported task |
| Unified Isaac Lab commands work with the selected installation | Smoke could fail before training | Run `make doctor`, then the short smoke | Use the explicit legacy command style for an older installation |
| The recovered controller can be adapted to the selected runtime | Live demo may need a different stream seam | Start one checkpoint and exercise status, frames, commands, reset, and checkpoint load | Keep recorded playback public and revise only the live adapter |
| A fresh run resembles the historical baseline | Article results may need revision | Compare its preserved metrics and rollouts | Publish the observed result, including regressions |

## Implementation path

1. Keep the local wrapper, evidence collector, and live-controller contract green.
2. On an approved GPU host, verify the installed task and run the checkpoint-producing smoke.
3. Run one bounded training and evaluation pass, preserve the complete evidence bundle, and update the article with the observed environment and result.
4. Revalidate the live controller through the existing lifecycle before each image or production release.

Exact versions, GPU selection, run size, checkpoint cadence, evaluation bar,
and streaming method are implementation-time choices. Record what passes the
real probes instead of predicting those details here.
