---
title: Running the official ACT policy on ALOHA cube transfer
summary: Replay a bimanual transfer on macOS, inspect its 100-action chunks, and keep the published benchmark separate from local runs.
collection: blog
category: tutorial
kind: tutorial
voice: product-lab
author: Robium team
audience: robotics-developer
level: intermediate
app: act-aloha-cube-transfer
date: 2026-08-28
tested: 2026-08-23
tags: [robium, lerobot, imitation-learning, act, aloha, mujoco, gradio, rerun, macos]
hero: assets/gifs/transfer-seed-1001.gif
hero_alt: Two simulated ALOHA arms pass a red cube between their grippers
social_image: assets/social/card.png
featured: false
---

One arm lifts a red cube and presents it near the center of the workspace. The
other closes around it and completes the transfer. ACT chooses the joint targets
in chunks of 100 actions, while MuJoCo reports each stage of the task.

The application runs LeRobot's official ALOHA Transfer Cube checkpoint. There
is no training step in the quick start. On Apple Silicon, inference uses MPS;
the hosted-compatible image uses CPU-only PyTorch.

![The official ACT checkpoint completing seed 1001](../assets/gifs/transfer-seed-1001.gif)

*A recorded MuJoCo rollout for seed 1001. The sidecar stores the checkpoint
revision, seed, device, action horizon, step count, and final simulator stage.*

## A task ACT was built for

ALOHA Transfer Cube is a bimanual imitation-learning task. The observation
contains a 480 by 640 top-camera image and fourteen joint-state values. Each
action also has fourteen values for the two arms and grippers.

Predicting one command at a time would leave a long control horizon. ACT,
Action Chunking with Transformers, predicts a sequence instead. This checkpoint
produces 100 future joint targets from the current observation, giving the two
arms a coherent movement before the next policy call.

LeRobot publishes a task-matched checkpoint at
`lerobot/act_aloha_sim_transfer_cube_human`. Its model card reports 83 percent
success over 500 evaluation episodes. That made it a better starting point than
training a new model for the sake of the demo.

> [!DECISION]
> ACT fit because the task is fixed, bimanual, and demonstration-driven.
> Diffusion Policy is a stronger starting point for PushT's contact geometry.
> A VLA belongs where language changes the requested object or action.

## From image to transfer

![ACT ALOHA system flow](../assets/diagrams/system.svg)

*The browser asks for a rollout. A child process keeps MuJoCo on its main
thread, while the policy predicts chunks and Rerun records the episode.*

The execution-horizon control decides how many actions from each prediction are
applied before ACT observes again. It does not select another checkpoint.

- `25/100` replans most often and spends more time in inference.
- `50/100` is useful for comparing the tradeoff.
- `100/100` executes the complete reference chunk.

Keep the layout seed fixed while comparing those settings. Seed 1001 is the
default because it completed the bounded MPS calibration and then completed
again on replay.

The direct camera frame remains the primary view. Rerun adds a timeline for
camera frames, task stage, policy calls, chunk indices, inference time, state,
and action values.

## Run it on macOS

You need Git, [uv](https://docs.astral.sh/uv/), a modern browser, and port 8765.
No NVIDIA GPU or physical robot is required.

```bash
npx robium-ai@latest setup
git clone https://github.com/robium-ai/robium-apps.git
cd robium-apps/act-aloha-cube-transfer
./app doctor
./app run
```

Open [http://localhost:8765](http://localhost:8765). The first run resolves the
Python 3.12 environment and downloads the pinned checkpoint source plus the
ResNet backbone. Later runs reuse the environment, migrated model, and cache.

The [application README](https://github.com/robium-ai/robium-apps/tree/main/act-aloha-cube-transfer)
covers the remaining launcher commands and troubleshooting paths.

## An older checkpoint in current LeRobot

The official checkpoint predates LeRobot's standalone preprocessor and
postprocessor files. A current loader cannot use the raw Hub snapshot directly.

LeRobot 0.6.1 includes a normalization migration. The application runs that
tool into a separate directory, removes the legacy normalization buffers from
the copied state dictionary, and creates processor files from the same stored
statistics. The original revisioned download stays untouched.

The build compares the remaining weights, checks the model and processor
artifacts, hashes the source and migrated files, and writes a manifest. A
partially migrated directory is not accepted as ready. Recomputing
normalization from another dataset could create plausible files while changing
the policy's behavior, so the migration does not substitute new statistics.

## What happened in the recorded runs

The workspace keeps two results separate:

- The official checkpoint model card reports 83 percent over 500 episodes.
- The local MPS calibration recorded two completions across seeds 1000 through
  1004 with the 100-action execution horizon.

Five local runs are useful for compatibility and replay checks. They are not a
new estimate of the published rate. The app stores unsuccessful runs as well as
completed ones and does not draw a learning curve between unrelated tests.

The simulator reports reaching, right-gripper contact, cube lifted,
left-gripper contact, and transfer complete. The UI uses those stage names. It
does not turn brief contact into a broader claim about grasp stability.

> [!EVIDENCE]
> Seed 1001 reached the simulator's terminal transfer stage with the 100-action
> execution horizon. The capture metadata records the conditions for that run.

## The browser changed the process boundary

On macOS, creating the gym-aloha environment from a Gradio worker thread raised
an AppKit exception because GLFW must initialize on the main thread.

Previews and episodes now run in spawned child processes. Each process creates
MuJoCo and GLFW on its own main thread, sends typed rollout events to the UI,
and closes the environment at the episode boundary. A bounded lock prevents two
browser jobs from mutating one simulator. Stop uses a shared cancellation event
and takes effect at the next simulator action.

The CPU image follows the same application contract with MuJoCo EGL rendering,
the migrated checkpoint, and a baked torchvision backbone cache. Readiness is
reported only after a CPU prediction returns a finite 100 by 14 action chunk.
On the tested Docker Desktop path, seed 1001 completed through the Gradio API;
its final policy call took 900 ms.

## A stricter pass bar

The `architect` and `lerobot` skills kept the project on a task where ACT had a
clear reason to exist. `environments` separated the native MPS path from the
CPU image instead of hiding both behind one performance claim. `testing` and
`rerun` shaped the migration checks, direct frame, typed timeline, and
separation between published and local results.

The most useful change was not visual. The pass bar moved from “the checkpoint
loads” to “a seeded rollout reaches a named simulator stage, records its
conditions, and can be stopped without corrupting the next run.”

## What this app does not cover

This application covers one simulated ALOHA task and one published checkpoint.
It does not train ACT, test physical arms, or estimate performance beyond the
attached run sets. Docker uses CPU inference, so native MPS remains the better
interactive path on Apple Silicon.

The source, smoke tests, and architecture brief live in the
[ACT ALOHA application](https://github.com/robium-ai/robium-apps/tree/main/act-aloha-cube-transfer).
