# Architecture Brief: Quadruped locomotion

**Date:** 2026-08-28
**Status:** active

## Goal and constraints

Publish a reference application that shows a Unitree Go2 learning to follow
velocity commands in Isaac Lab. Visitors should always be able to compare real
recorded checkpoints. A paid live session may additionally expose the running
simulator and movement controls.

Isaac Lab does not run on the development Mac, so real simulation, smoke,
training, and live validation happen on a compatible remote NVIDIA GPU. Paid
allocation, artifact publication, and deployment are separate approval points.

## Decisions

| Decision | Choice | Why now | Confidence |
|---|---|---|---|
| First working slice | Recorded checkpoint progression backed by the recovered run | Useful without a running GPU and exposes real behavior immediately | validated |
| Training path | Existing Isaac Lab Go2 velocity task with RSL-RL | It produced the recovered walking policy and remains the shortest route to the requested result | validated |
| Environment | Thin local Python wrapper plus an installed Isaac Lab GPU environment | Local code stays testable while simulator ownership remains upstream | validated |
| Live experience | Reuse the verified frame stream and controls, then connect it to the existing RunPod lifecycle | Preserves the working interaction before exploring alternatives | provisional |
| Artifact home | Hugging Face evidence repository | Keeps large checkpoints and videos outside Git with an immutable revision | provisional until publication |

## Provisional assumptions and risks

| Assumption or risk | Impact | Cheapest validation | Authorized pivot |
|---|---|---|---|
| The installed Isaac Lab still registers the Go2 flat task | Training cannot start if the task moved | Run `make list-envs` on the GPU host | Update the task name or nearby supported task |
| Unified Isaac Lab commands work with the selected installation | Smoke could fail before training | Run `make doctor`, then the short smoke | Use the explicit legacy command style for an older installation |
| The recovered controller can be adapted to the selected runtime | Live demo may need a different stream seam | Start one checkpoint and exercise status, frames, commands, reset, and checkpoint load | Keep recorded playback public and revise only the live adapter |
| A fresh run resembles the historical baseline | Article results may need revision | Compare its preserved metrics and rollouts | Publish the observed result, including regressions |

## Implementation path

1. Keep the local wrapper, evidence collector, and recorded explorer green.
2. On an approved GPU host, verify the installed task and run the checkpoint-producing smoke.
3. Run one bounded training and evaluation pass, preserve the complete evidence bundle, and update the article with the observed environment and result.
4. Validate the live controller through the existing lifecycle before enabling paid public capacity.

Exact versions, GPU selection, run size, checkpoint cadence, evaluation bar,
and streaming method are implementation-time choices. Record what passes the
real probes instead of predicting those details here.
