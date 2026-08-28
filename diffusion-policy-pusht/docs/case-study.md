---
title: Why PushT needed Diffusion Policy
summary: A failed ACT configuration led to a task-matched checkpoint, a careful compatibility adapter, and a faster way to inspect PushT on macOS.
collection: blog
category: tutorial
kind: tutorial
voice: product-lab
author: Robium team
audience: robotics-developer
level: intermediate
app: diffusion-policy-pusht
date: 2026-08-28
tested: 2026-08-22
tags: [robium, lerobot, imitation-learning, diffusion-policy, act, pusht, gradio, rerun, macos]
hero: assets/gifs/workspace-rollout.gif
hero_alt: A blue circular agent pushes a gray T-shaped block toward a green target
social_image: assets/social/card.png
featured: false
---

This project began with the wrong policy contract. We trained ACT checkpoints
at 1k, 3k, 5k, and 10k steps, but none completed PushT. The policy observed one
frame and could execute a 100-action chunk at 10 Hz, which was most of an
episode before it looked again.

More training would not fix that control loop. We kept the unsuccessful runs,
changed direction, and built the application around LeRobot's published
Diffusion Policy checkpoint instead.

![A seeded PushT rollout in the application workspace](../assets/gifs/workspace-rollout.gif)

*A recorded rollout from the browser workspace. The live frame stays visible
while the policy replans and Rerun records the trajectory.*

## PushT is small, but the contacts are not simple

[PushT](https://huggingface.co/datasets/lerobot/pusht) uses a circular agent to
push a T-shaped block into a green target. The observation is a 96 by 96 RGB
image plus the agent position. The action is the next 2D position command. An
episode succeeds when the block covers more than 95 percent of the target.

The policy has to choose useful contact points, rotate and translate the block,
recover after losing contact, and handle different initial layouts. Several
action sequences can make sense from the same image.

Diffusion Policy fits that shape of problem. It starts with a noisy action
sequence and refines it while conditioning on the current observation. PushT is
also an established evaluation task for the method, and LeRobot publishes a
task-matched checkpoint with a 500-episode result.

> [!DECISION]
> ACT remains a useful baseline for demonstration-driven manipulation, but our
> execution horizon did not fit PushT. A VLA would add language and model cost
> to a task whose objective is entirely geometric. Diffusion Policy matched the
> behavior and the available checkpoint.

## What runs between the frame and the next move

![PushT Diffusion Policy system flow](../assets/diagrams/system.svg)

*The policy turns the current image and agent state into a denoised action
sequence. The simulator executes a short horizon, then the policy observes
again.*

The workspace exposes two inference settings. Fast uses 10 denoising steps for
more responsive local interaction. Reference uses 100 steps, matching the
published evaluation schedule. The setting changes inference compute, not the
model weights.

The T shape routes directly to the upstream `gym_pusht/PushT-v0` environment.
L, I, and Z are qualitative geometry probes built locally. They are useful for
watching behavior outside the benchmark, but they were not part of the
checkpoint's training task.

Keep the layout seed fixed when comparing settings. Seeds 1000 through 1499
match the official evaluation range; other seeds are labeled qualitative.

## Run the native Mac path

The tested local path uses Apple Silicon, [uv](https://docs.astral.sh/uv/),
ffmpeg, a modern browser, and port 8765. It does not require an NVIDIA GPU,
physical robot, or training run.

```bash
npx robium-ai@latest setup
git clone https://github.com/robium-ai/robium-apps.git
cd robium-apps/diffusion-policy-pusht
./app doctor
./app run
```

Open [http://localhost:8765](http://localhost:8765). The first build downloads
roughly 1 GB for the pinned model. Native PyTorch uses MPS; the optional Docker
image uses CPU inference because Docker Desktop cannot expose Metal to Linux.

The [application README](https://github.com/robium-ai/robium-apps/tree/main/diffusion-policy-pusht)
contains the remaining launcher commands and setup details.

## The checkpoint adapter had to preserve old statistics

The checkpoint is pinned to revision
`84a7c23178445c6bbf7e1a884ff497017910f653`. It predates LeRobot 0.6's separate
`policy_preprocessor.json` and `policy_postprocessor.json` files, so a current
loader cannot open the repository as published.

Our first adapter generated processors from the current PushT dataset. The
model loaded, but its behavior was poor. The checkpoint already contained the
normalization buffers it expected, including ImageNet image mean and standard
deviation, and those values differed from the current dataset statistics.

The application now reads the embedded image, state, and action buffers,
creates current processor files from those tensors, leaves the weights
unchanged, records the source revision, and checks tensor equality before
inference.

The environment needed the same care. A custom T looked right but had different
inertia from the benchmark. The reference path now uses the upstream T exactly;
only the optional letter probes use custom geometry.

## What the runs say

LeRobot's model card reports 65.4 percent success and 0.955 average maximum
normalized reward over 500 episodes for the official checkpoint.

The stopped local 5k ACT experiment recorded one success in 30 completed
episodes. It remains available as a separate experiment, not as a point on the
official checkpoint's curve.

After the processor and environment fixes, a native Reference rollout on seed
1000 completed in 231 steps, reached 0.955 maximum raw coverage, and took 164
seconds on the tested Apple M5. The container path later completed the same
seed in 116 steps at 0.953 raw coverage.

![A completed seeded rollout with its Rerun timelines](../assets/stills/solved-rerun-timeline.png)

*The direct frame shows the final layout. Rerun aligns observation, action, and
target-coverage timelines for the same episode.*

> [!EVIDENCE]
> These seeded episodes check the adapter and runtime paths. The published
> 500-episode result remains the larger evaluation.

## From local workspace to a temporary browser session

The local process uses MPS and remains the faster Mac experience. The website
path uses a multi-stage CPU image containing the pinned checkpoint, processor
files, application source, and Linux-only CPU PyTorch wheels. Hub access is
disabled at runtime.

A FastAPI gateway mounts Gradio at `/ui` and exposes start, status, and shutdown
for one private session. The policy loads in the background, rollouts are
serialized, and the session expires after 30 minutes. Local container testing
covered claim isolation, the visible observation, a complete rollout, and
container removal on Stop.

## The failed policy stayed useful

The `lerobot` skill helped separate a policy choice from a configuration
mistake. `testing` kept the failed ACT run, stopped local benchmark, official
checkpoint result, and individual rollouts from becoming one misleading chart.
`environments` preserved the native MPS path while `live-demo` and `integration`
shaped the CPU image and private-session boundary.

The most consequential test was not “the checkpoint loads.” It compared the
adapter's tensors with the values embedded in the pinned model, used the
upstream T dynamics, and ran a seeded episode to completion.

## Where the comparison stops

This application runs an existing checkpoint. It does not establish that
Diffusion Policy is the best choice for every contact task, and the L, I, and Z
shapes are qualitative probes rather than benchmark results. Fast inference
uses fewer denoising steps than the published schedule. The CPU container is
convenient for delivery, but native MPS remains quicker on Apple Silicon.

Source, smoke tests, and the architecture brief are available in the
[PushT application](https://github.com/robium-ai/robium-apps/tree/main/diffusion-policy-pusht).
