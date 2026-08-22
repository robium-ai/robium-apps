# PushT with Diffusion Policy: application redesign

**Date:** 2026-08-21  
**Current application:** `imitation-manipulation`  
**Approved application id:** `diffusion-policy-pusht`  
**Display title:** PushT with Diffusion Policy  
**Status:** Direction and name approved in conversation; this written specification awaits review.

## 1. Goal

Replace the undertrained ACT-on-PushT reference application with a task-matched
visual Diffusion Policy application that:

- trains and evaluates natively on Apple Silicon through MPS;
- produces a real checkpoint learning curve rather than a decorative ladder;
- measures success on identical randomized PushT layouts;
- lets a visitor replay or randomize a layout against any checkpoint;
- presents the live RGB rollout even if the embedded Rerun viewer fails; and
- uses the same dark, compact workspace language as the Robot Navigation demo.

This is a replacement, not an ACT compatibility mode. Existing ACT checkpoints,
ACT metrics, ACT copy, and the `robium/pusht-act-ladder` artifact contract do not
remain part of the renamed app. A separate future `act-pick-and-place` app will
demonstrate ACT on a task that fits it.

## 2. Scope and repositories

### robium-apps

- Rename `imitation-manipulation/` to `diffusion-policy-pusht/`.
- Rename the Python distribution and import package to
  `diffusion-policy-pusht` and `diffusion_policy_pusht`.
- Replace ACT training, checkpoint, evaluation, runner, manifest, and copy with
  Diffusion Policy equivalents.
- Retain the PushT environment and the existing L/I/Z geometry variants as
  explicitly out-of-distribution probes.
- Rebuild README, architecture brief, case study, `robium-app.yaml`, thumbnail,
  Make targets, and the `REGISTRY.md` entry around the new contract.
- Update the existing smoke and demo-smoke checks; do not add new test files.

### robium-website

- Replace the legacy `manip-trial` route/component copy with
  `diffusion-policy-pusht`.
- Match the Robot Navigation workspace shell: dark full-height canvas, Robium
  brand/status bar, restrained borders, compact controls, and responsive mobile
  layout.
- Keep local/direct-host operation honest until a hosted instance exists.
- Do not deploy, publish, upload artifacts, or mutate cloud resources without a
  separate explicit instruction.

The website work begins only after the application and demo smokes pass. The
demo is a consumer of a working app, not a substitute for one.

## 3. Policy choice and training contract

Use LeRobot 0.6.0's visual `diffusion` policy with `lerobot/pusht`. The installed
Diffusion configuration describes its defaults as PushT-specific; the app will
make the relevant values explicit in its config and generated manifest so a
future library-default change cannot silently alter the experiment.

Initial training recipe:

| Setting | Value | Reason |
| --- | ---: | --- |
| policy | `diffusion` | Task-matched multimodal action model |
| observations | two frames | Current and previous 10 Hz observation |
| prediction horizon | 64 actions | Current LeRobot PushT default |
| executed actions | calibrated from 8, 16, 32 | Preserve feedback while measuring the current default |
| training diffusion steps | 100 | Current LeRobot PushT default |
| inference diffusion steps | calibrated from 10 and 100 | Compare live latency against policy quality |
| vision encoder | pretrained ResNet-18 | Current LeRobot PushT default |
| batch size | 8 initially | Known MPS-safe starting point; increase only after measurement |
| optimizer/scheduler | policy preset | Avoid reconstructing an unofficial recipe |
| seed | 1000 | Reproducible training baseline |
| total steps | 100,000 | LeRobot's standard full training budget |
| checkpoints | 5k, 10k, 25k, 50k, 75k, 100k | Early signal plus useful learning curve |

Training proceeds in two gates:

1. **Pipeline gate:** train 200 steps, save the processor-era checkpoint, and
   complete a two-episode synchronous eval. This proves the local dataset,
   Diffusion dependencies, processors, MPS path, and evaluator agree. It has no
   success threshold.
2. **Learning gate:** train through 5k, evaluate the candidate execution and
   denoising settings on a fixed calibration seed set, choose one execution
   contract, then resume the same run through 100k. All ladder checkpoints use
   the chosen execution contract so training progress remains comparable.

The app records measured wall time, steps per second, device, effective policy
configuration, and LeRobot version in the generated manifest. Training may be
resumed, and a resumed run keeps its checkpoint config rather than silently
adopting new defaults.

## 4. Evaluation and checkpoint selection

The benchmark set is 50 fixed, randomized T-layout seeds disjoint from the
small calibration set. Every retained checkpoint runs on the same seeds with:

- `pc_success` at PushT's native 95% coverage threshold;
- average and median maximum coverage;
- average cumulative reward;
- completion step for successful episodes;
- per-seed result records; and
- representative rollout videos.

The default demo checkpoint is selected by highest `pc_success`, then average
maximum coverage, then the earlier checkpoint. It is never selected merely
because it is the latest checkpoint.

The target release bar is at least **70% success over the fixed 50-seed T
benchmark**. Eighty percent is the stretch target suggested by published visual
Diffusion Policy PushT results. If 100k does not reach 70%, the app remains in
development and the evidence drives one controlled change at a time; the UI
does not relabel partial coverage as success.

L/I/Z runs do not contribute to the benchmark or release threshold. They are
live out-of-distribution probes because the training dataset contains only T.

## 5. Artifact and manifest contract

One generated `outputs/demo/ladder.json` remains the source of truth for both
training evidence and the demo. Its new schema contains:

- policy family and complete effective policy config;
- training run id, seed, device, library versions, and checkpoint steps;
- the fixed benchmark seed list and evaluation count;
- per-checkpoint aggregate metrics and per-seed results;
- checkpoint-relative paths and representative video paths;
- the selected default checkpoint and the deterministic tie-break reason; and
- calibration results for action and inference horizons.

The demo never hardcodes performance numbers. A missing checkpoint, processor
file, metric field, or video produces a precise preflight failure rather than a
partially populated page.

Large checkpoints and videos stay under ignored `outputs/` locally. A new Hub
artifact repository name can be chosen only when artifact publication is
explicitly authorized. Until then, the implemented app runs from locally
trained outputs and does not overwrite or depend on the old ACT repository.

## 6. Live demo interaction design

The demo remains a Gradio application because it provides a small Python-native
surface over the policy runner. It adopts a workspace rather than notebook
layout.

### Header

- Robium mark and wordmark.
- “PushT with Diffusion Policy”.
- Health state: loading, ready, running, finished, or error.
- Active device and selected checkpoint.
- Run/Stop control; Stop cooperatively aborts an orphaned or unwanted rollout.

### Left control rail

- Checkpoint cards ordered by training step, each showing success rate and
  maximum coverage from the fixed benchmark.
- Shape selector: T is labeled benchmark; L/I/Z are labeled OOD.
- Seed control with `Randomize layout` and `Replay this seed` actions.
- Run button and concise explanation of the 95% success criterion.

Random means drawing a seed, not mutating hidden state. The actual seed is
always displayed and included in the final result so a run can be replayed
against another checkpoint.

### Main rollout pane

- A direct `gr.Image` stream is the primary visual truth and starts with a real
  reset frame before the first run.
- Frames are enlarged from the policy's 96×96 observation without changing the
  pixels sent to the policy.
- A compact overlay/readout shows step, current coverage, maximum coverage,
  action target, and success state.
- A result card distinguishes solved, partial progress, aborted, and runtime
  error.

### Evidence pane

- Checkpoint performance chart with training step on the x-axis and success
  rate plus average maximum coverage on the y-axis.
- A same-seed comparison view that can replay benchmark videos from multiple
  checkpoints.
- Rerun timeline for image, action, and reward telemetry. Rerun is additive:
  a black or unavailable embedded canvas cannot hide the direct live frame or
  block a run.

Desktop uses a control rail plus large rollout pane; smaller screens stack
controls, rollout, and evidence without horizontal overflow. Styling mirrors
Robot Navigation's near-black canvas, 62 px status bar, blue primary action,
subtle white borders, compact typography, and visible health dot.

## 7. Runner and state model

The runner lazily loads checkpoints and caches them by rung. Each run accepts
`checkpoint`, `shape`, and `seed`; it returns frame-bearing step events and a
final structured result. It owns:

- the policy/preprocessor/postprocessor triple;
- a serial run lock;
- a cooperative cancellation event;
- environment construction and explicit seed reset;
- direct RGB frames and scalar telemetry; and
- deterministic cleanup on completion, error, cancellation, or page refresh.

The browser can generate a random seed, but the runner accepts and reports the
resolved integer. A refresh or disconnected Gradio generator must not retain the
single run lock indefinitely.

Checkpoint loading validates Diffusion Policy type and required processor files
before entering the episode. Errors name the selected checkpoint and missing
contract rather than falling through to Hub-id resolution.

## 8. Verification

Repository policy forbids adding tests without explicit approval, so existing
checks are updated in place.

### Existing default smoke

- A 200-step Diffusion Policy training run completes on MPS or the documented
  CPU fallback.
- The saved checkpoint contains weights, config, and both processor files.
- A two-episode synchronous eval exits successfully and emits numeric metrics.

### Existing demo smoke

- The renamed app reaches `DEMO READY` with a real reset frame.
- A seeded T run completes through the Gradio API and returns non-black,
  non-flat image frames plus a structured result.
- An L run completes and is explicitly marked out-of-distribution.
- Replaying the same seed preserves the initial layout.
- Cancellation releases the existing run lock.

These assertions extend the flows already collected from `tests/test_smoke.py`
and `tests/test_demo.py`; implementation does not add a test module or increase
the collected test count.

### Real validation

- Run the complete 50-seed benchmark for every retained checkpoint.
- Confirm the selected default satisfies the 70% success release bar.
- Open the demo in a real browser on macOS and verify the reset frame, streamed
  episode, checkpoint chart, same-seed replay, responsive layout, and Rerun
  fallback behavior.
- Run the renamed app's `make check`, default smoke, demo smoke, and native
  demo from the documented clean setup.
- Update README and `REGISTRY.md` with the actual measured Mac timings and last
  verified date in the same implementation commit.

No deployment or artifact upload is part of verification.

## 9. Implementation sequence

1. Rename the directory, package, manifest, imports, commands, and registry
   identity while preserving unrelated worktree changes.
2. Replace ACT config/runner/ladder code with Diffusion Policy and pass the
   200-step pipeline smoke.
3. Train to 5k, calibrate the execution contract, and confirm measurable
   learning before committing to the long run.
4. Resume to 100k, evaluate the fixed 50-seed ladder, and select the default
   checkpoint from generated evidence.
5. Rebuild the Gradio UI around direct frames, replayable seeds, performance
   comparison, optional Rerun telemetry, and cooperative cancellation.
6. Pass the existing app and demo smokes plus manual browser validation.
7. Update documentation, architecture brief, case study, thumbnail, manifest,
   and registry with measured results.
8. Update the website route/workspace to the approved identity and navigation
   theme, then run its local build/checks. Stop before any deployment or upload.

## 10. Explicit non-goals

- Preserve or expose the old ACT checkpoints.
- Train on L/I/Z or claim they are benchmark generalization.
- Add language conditioning or SmolVLA to this application.
- Build the future ACT pick-and-place application in this change.
- Add new test files.
- Deploy the site, publish an image, upload checkpoints, or create cloud
  infrastructure.

## 11. Verified inputs

- Local preflight on 2026-08-21: macOS arm64, MPS available, Docker healthy,
  uv 0.11.29, and 437 GB free.
- Installed LeRobot 0.6.0 Diffusion config: two observations, horizon 64,
  32 executed actions, 100 diffusion timesteps, pretrained ResNet-18, and
  PushT-specific defaults.
- Installed LeRobot training config: 100,000 default training steps.
- Upstream Diffusion Policy visual PushT benchmark: convolutional policy
  reported 0.91 best / 0.84 last-ten-checkpoint average coverage score across
  the paper's evaluation protocol. This motivates, but does not substitute for,
  this app's own fixed-seed success evaluation.
- Upstream sources checked on 2026-08-21:
  [LeRobot Diffusion configuration](https://github.com/huggingface/lerobot/blob/main/src/lerobot/policies/diffusion/configuration_diffusion.py),
  [LeRobot PushT Diffusion training example](https://github.com/huggingface/lerobot/blob/main/examples/training/train_policy.py),
  [LeRobot installation](https://github.com/huggingface/lerobot/blob/main/docs/source/installation.mdx),
  and [Diffusion Policy](https://diffusion-policy.cs.columbia.edu/diffusion_policy_ijrr.pdf).
