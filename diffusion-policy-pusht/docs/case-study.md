---
title: Run a published Diffusion Policy on macOS with LeRobot and PushT
summary: Use Robium's PushT reference app to compare policy choices, replay seeded layouts, and inspect a published Diffusion Policy without training it first.
collection: blog
category: tutorial
kind: tutorial
voice: technical
author: Robium team
audience: robotics-developer
level: intermediate
app: diffusion-policy-pusht
date: 2026-08-22
tested: 2026-08-22
tags: [robium, lerobot, imitation-learning, diffusion-policy, act, smolvla, pusht, gradio, rerun, macos]
hero: assets/thumbnail.png
hero_alt: PushT Diffusion Policy evidence and live rollout workspace
social_image: assets/thumbnail.png
featured: false
---

We built this manipulation application with
[Robium](https://robium.ai/). Its skills helped us choose a policy for the
task, keep the environment fast on Apple Silicon, evaluate the result against
repeatable seeds, and turn the working policy into a local and browser-hosted
reference app.

The project began as a training demonstration. We wanted to show checkpoints
improving as a policy learned to push a T-shaped block into a target. That
version trained an ACT policy locally, but the 1k, 3k, 5k, and 10k checkpoints
never solved the task. Continuing to train and benchmark that configuration
would have made the demo slower without answering the more useful question:
what policy should we use for PushT?

We changed direction. The current application starts from LeRobot's published
Diffusion Policy checkpoint, preserves its evaluation evidence, and lets you
run fresh seeded episodes on a Mac or in a CPU container. Training remains
available for research, but it is no longer a prerequisite for opening the
application.

**PushT with Diffusion Policy** is also a living Robium reference application.
The problems we found while loading the older checkpoint, comparing metrics,
streaming live frames, and packaging the CPU runtime were captured as
learnings for future manipulation projects.

> **Robium skills used:**
> [architect](https://github.com/robium-ai/robium/tree/main/skills/architect)
> helped frame the application around a concrete benchmark;
> [lerobot](https://github.com/robium-ai/robium/tree/main/skills/lerobot)
> guided the policy and checkpoint workflow; and
> [environments](https://github.com/robium-ai/robium/tree/main/skills/environments)
> kept native MPS and reproducible CPU delivery as separate, explicit paths.

## What PushT tests

[PushT](https://huggingface.co/datasets/lerobot/pusht) is a compact visual
manipulation benchmark. A circular agent pushes a T-shaped block across a 2D
workspace. The goal is to align the block with a green target region.

The observation is a 96×96 RGB image plus the agent position. The action is
the next 2D position command. An episode succeeds when the block covers more
than 95% of the target.

The environment is small enough to run on a laptop, but the behavior is not
trivial. The policy must make contact at useful points, rotate and translate
the block, recover when contact is lost, and approach the target from
different initial layouts. Several action sequences may be reasonable from
the same visual state.

That makes PushT a useful policy-selection exercise. The simulator is simple;
the interesting part is how the policy represents and generates behavior.

## ACT, Diffusion Policy, or SmolVLA?

LeRobot supports several policy families behind a common dataset and training
workflow. Three of the most relevant starting points are ACT, Diffusion
Policy, and SmolVLA. They solve different problems.

| Policy | What it predicts | Good starting point when | Main cost |
| --- | --- | --- | --- |
| ACT | A chunk of future actions from observations and robot state | The task is well represented by demonstrations and you want a compact imitation-learning baseline | Chunk length and execution horizon need task-specific tuning |
| Diffusion Policy | An action sequence refined through iterative denoising | The task has contact-rich or multimodal behavior and a strong task-matched checkpoint or dataset exists | Each plan requires several network evaluations |
| SmolVLA | Language-conditioned action chunks from images, state, and an instruction | Language and task-level semantic variation are part of the problem | More model capacity, data preparation, and fine-tuning compute |

[ACT](https://arxiv.org/abs/2304.13705), or Action Chunking with Transformers,
was developed for fine-grained manipulation. Predicting a sequence rather
than one action at a time can smooth behavior and reduce the effective
planning horizon. LeRobot recommends ACT as a practical first policy, and it
was a sensible first experiment here.

Our mistake was treating an ALOHA-oriented default configuration as if it were
already tuned for PushT. The policy observed one frame and could execute a
100-action chunk. At the environment's 10 Hz control rate, that was most of an
episode before the next observation. Training more steps would not correct
that execution contract. The failed result was evidence about our
configuration, not a general verdict on ACT.

[Diffusion Policy](https://diffusion-policy.cs.columbia.edu/) generates an
action sequence by starting from noise and repeatedly denoising it while
conditioning on the current observation. The method was designed to represent
multimodal action distributions and uses receding-horizon control. PushT is
one of its established evaluation tasks, and LeRobot publishes a task-matched
checkpoint with a 500-episode result. That combination made it the strongest
reference choice for this application.

[SmolVLA](https://huggingface.co/docs/lerobot/smolvla) is a compact
vision-language-action model. It accepts multiple camera views, robot state,
and a natural-language instruction, then generates an action chunk. We would
choose it when instructions such as “place the red block in the left bin” and
variation across tasks or objects are part of the application. PushT has one
geometry-driven objective and no language input. Adding a VLA would increase
the training and runtime surface without giving the policy useful information
for this benchmark.

The practical rule is simple: start with the least complex policy that matches
the task. ACT remains a good baseline for many demonstration-driven
manipulation tasks. Diffusion Policy earned its place here because the behavior
and available checkpoint matched PushT. SmolVLA belongs in an application
where language conditioning is a requirement rather than a label added after
the fact.

> **Robium skills used:**
> The
> [lerobot](https://github.com/robium-ai/robium/tree/main/skills/lerobot)
> skill supplied the policy and evaluation framework. The
> [testing](https://github.com/robium-ai/robium/tree/main/skills/testing)
> skill kept the failed ACT checkpoints, the incomplete local Diffusion run,
> and the published checkpoint from being mixed into one misleading curve.

## System requirements

The native application is tested on Apple Silicon macOS. You need:

- Git;
- [uv](https://docs.astral.sh/uv/);
- ffmpeg;
- a modern browser;
- port 8765 available.

No NVIDIA GPU, physical robot, or local training run is required. The first
build downloads roughly 1 GB for the pinned model.

Docker is optional. It is used for the website-compatible CPU image and local
hosted-demo testing. Docker Desktop on macOS cannot expose the Mac's Metal
accelerator to a Linux container, so the native path is the faster choice for
interactive use.

## Install Robium and start the application

Install the Robium skills, then clone the applications repository:

```bash
npx robium-ai@latest setup
git clone https://github.com/robium-ai/robium-apps.git
cd robium-apps/diffusion-policy-pusht
```

Install ffmpeg if it is not already available:

```bash
brew install ffmpeg
```

Use the repository-local launcher:

```bash
./app help
./app doctor
./app run
```

`doctor` checks uv, ffmpeg, the lockfile, checkpoint readiness, port 8765,
and optional Docker availability. It does not install packages or change the
running system.

`run` prepares the uv environment and pinned checkpoint when needed, then
starts the native policy workspace. This is the same six-command application
surface used by the Robot Navigation reference app: `doctor`, `build`,
`run`, `status`, `logs`, and `stop`.

Open [http://localhost:8765](http://localhost:8765).

> **Robium skills used:**
> [environments](https://github.com/robium-ai/robium/tree/main/skills/environments)
> guided the uv-first native setup. The optional Docker image remains a
> separate CPU path because hiding it behind the default command would make
> inference substantially slower on a Mac.

## Read the policy workspace

The control panel is organized as an experiment rather than a polished video
player. Each control changes one part of the rollout contract.

### Policy evidence

**Official LeRobot 175k** is the default. The
[model card](https://huggingface.co/lerobot/diffusion_pusht) reports 65.4%
success and 0.955 average maximum normalized reward over 500 episodes.

**Local 5k experiment** preserves the separate training attempt. Its benchmark
was stopped after 30 of 50 episodes, with one success. It remains visible
because failed and incomplete results are useful evidence, but the chart does
not connect it to the official checkpoint. The models were trained with
different configurations.

### Inference quality

The **Fast** setting uses 10 denoising steps. It makes local interaction more
responsive, but it does not inherit the official success claim.

The **Reference** setting uses 100 denoising steps, matching the published
checkpoint's evaluation schedule. It takes longer because every replan
performs 100 refinement passes.

Changing this control does not retrain or modify the model. It changes how much
compute is used to turn noise into the next action sequence.

### Block shape and layout seed

T is the benchmark. It runs in the original upstream PushT environment.

L, I, and Z are qualitative out-of-distribution probes. They use the same
policy with a generalized local geometry builder, but those letters were not
part of the model's training task.

The seed controls the initial agent, block, and target layout. Keep it fixed
when comparing policy evidence or inference quality. Randomize it when you
want another layout. Seeds 1000 through 1499 correspond to the official
evaluation range; other seeds are labeled qualitative.

### Live observation and Rerun

The live 96×96 RGB frame is the primary view. It remains visible while the
policy runs and does not depend on an external viewer.

Rerun adds a timeline for observations, actions, and target coverage. You can
pause and scrub through a rollout to inspect where contact changed or where a
planned sequence stopped making progress.

> **Robium skills used:**
> [rerun](https://github.com/robium-ai/robium/tree/main/skills/rerun)
> guided the rollout timeline. The
> [live-demo](https://github.com/robium-ai/robium/tree/main/skills/live-demo)
> skill kept the direct RGB frame primary and treated richer telemetry as an
> additive debugging surface.

## Why the official checkpoint needed an adapter

The checkpoint is pinned to revision
`84a7c23178445c6bbf7e1a884ff497017910f653`. Its weights are not modified.

It was published before LeRobot 0.6 separated normalization into
`policy_preprocessor.json` and `policy_postprocessor.json`. Loading the
repository directly under LeRobot 0.6 therefore fails because those files are
missing.

The first compatibility attempt generated processors from the current PushT
dataset statistics. The model loaded, but its behavior was poor. Inspection of
the original checkpoint showed why: it already contained the normalization
buffers it expected, including ImageNet image mean and standard deviation.
The current dataset's pixel statistics were different.

The application now performs a deterministic conversion:

1. Fetch the pinned checkpoint revision.
2. Read its embedded image, state, and action normalization buffers.
3. Create LeRobot 0.6 processor files with those exact tensors.
4. Keep the original model weights unchanged.
5. Write a provenance file recording the source revision and conversion.
6. Assert tensor equality before running the policy.

The environment needed the same care. A custom T builder looked visually
correct but produced different inertia from the upstream benchmark. The
official T option now routes directly to `gym_pusht/PushT-v0`; only L, I,
and Z use custom geometry.

After both corrections, a native 100-denoise rollout on official seed 1000
solved the task in 231 steps, reached 0.955 maximum raw coverage, and took 164
seconds on the tested Apple M5. That episode is a runtime and compatibility
check, not a replacement for the published 500-episode benchmark.

> **Robium skills used:**
> The
> [testing](https://github.com/robium-ai/robium/tree/main/skills/testing)
> skill pushed us beyond “the checkpoint loads” to exact processor assertions,
> upstream-environment parity, and a full seeded rollout. The
> [lerobot](https://github.com/robium-ai/robium/tree/main/skills/lerobot)
> skill identified the processor-era checkpoint boundary that the adapter
> needed to cross.

## Local and website delivery

The same experiment workspace has two runtime paths.

The local path uses uv and native PyTorch. On Apple Silicon, LeRobot selects
MPS. The `./app` launcher records the process and log so another terminal can
inspect or stop it without searching for a Python process manually.

The website path uses a multi-stage CPU image. The build stage resolves
Linux-only CPU PyTorch wheels, prepares the processor files, and fetches the
pinned checkpoint. The runtime stage receives only the environment,
checkpoint, and application source. Hub access is disabled at runtime.

A small FastAPI gateway mounts Gradio at `/ui` and provides the same
start/status/shutdown contract used by Robium's live-demo orchestrator. The
policy loads in the background so lifecycle status remains responsive. Each
container accepts one session claim, serializes rollouts, and expires after 30
minutes.

Local verification exercised the full website path. Start created a private
container, BOOTING advanced to READY, the observation stayed visible, a live
rollout solved seed 1000 in 116 steps at 0.953 raw coverage, and Stop removed
the container.

> **Robium skills used:**
> [integration](https://github.com/robium-ai/robium/tree/main/skills/integration)
> kept the policy, simulator, UI, and lifecycle gateway in one supervisable
> runtime. The
> [live-demo](https://github.com/robium-ai/robium/tree/main/skills/live-demo)
> skill defined the private-session lifecycle and browser acceptance checks.

## How Robium helped build this application

Robium was useful here because the difficult parts sat between tools rather
than inside one model class.

It helped us:

- **Choose a task-matched policy.** The first ACT run was treated as evidence,
  then the LeRobot workflow was re-evaluated against the actual PushT task.
- **Keep claims comparable.** Published evaluation, a stopped local benchmark,
  and individual live rollouts are labeled separately.
- **Preserve Mac performance.** Native MPS remains the default while the CPU
  image serves reproducibility and website delivery.
- **Debug checkpoint compatibility.** The final processor conversion follows
  the tensors embedded in the pinned model instead of silently substituting
  current dataset statistics.
- **Test behavior, not just startup.** Seeded T and OOD rollouts, cancellation,
  frame continuity, session isolation, and container teardown all belong to
  the pass bar.
- **Feed the failures back.** The ACT configuration mismatch, legacy processor
  conversion, environment dynamics drift, Gradio frame replacement, and CPU
  wheel resolution are now captured as reusable Robium learnings.

The result is a working application and a reference for deciding how a learned
manipulation policy should be evaluated, packaged, and explained.

## Inspect and stop the application

Use the same launcher from another terminal:

```bash
./app status
./app logs
./app help
./app stop
```

`status` prints the process ID, URL, and log path. `logs` follows model
loading and server output. Pressing Ctrl-C in the original `run` terminal
also stops the workspace cleanly.

[Install Robium](https://robium.ai/#install) to use the same skills in your
own robotics project.

The source is available in the
[PushT with Diffusion Policy application](https://github.com/robium-ai/robium-apps/tree/main/diffusion-policy-pusht).
The repository also contains the
[architecture brief](https://github.com/robium-ai/robium-apps/blob/main/diffusion-policy-pusht/docs/architecture-brief.md)
and the complete local and container smoke tests.

This project demonstrates one visual policy in a 2D simulator. The official
success rate remains 65.4%, L/I/Z are qualitative probes, and a successful
seed does not establish a new benchmark. Moving the same approach to a
physical arm requires new demonstrations, camera and action calibration,
safety limits, and evaluation on the target hardware.
