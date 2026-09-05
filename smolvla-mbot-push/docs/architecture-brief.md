# Architecture Brief: SmolVLA mBot Push

**Date:** 2026-08-30
**Status:** active

## Goal and constraints

**Outcome.** A differential-drive robot pushes a block to a goal, driven by a
SmolVLA policy fine-tuned on demonstrations recorded with a game controller. The
policy's only observation is a fixed overhead camera.

**Scope right now: simulation only.** A real Makeblock mBot is the eventual
target, but no hardware work is in scope until the simulated pipeline -
record, train, evaluate - works end to end. An earlier draft carried a firmware
sketch, a Bluetooth serial driver, and a webcam capture path; all removed as
premature.

**Why this app.** The cheapest credible physical-AI pipeline to learn from: one
small robot, one camera, one controller. It is the sibling of
`diffusion-policy-pusht`, which runs the same class of task with a different
policy family.

**Constraints.**
- Runs on the maintainer's Mac; installs in seconds, needs no GPU to drive.
- Training will run on a rented remote GPU, following `vla-pick-and-place`.

## Decisions

| Decision | Choice | Why now | Confidence |
|---|---|---|---|
| Build order | Simulation first, hardware later | The largest risk is whether SmolVLA fine-tunes to a 2-DoF nonholonomic base, and sim answers that with free resets and unlimited episodes | validated |
| Simulator | MuJoCo, hand-built scene | Non-ROS, contact-rich, native and fast on Apple Silicon. No off-the-shelf diff-drive push env exists, and the scene is small enough to own | validated |
| Policy | SmolVLA (LeRobot, ~450M) | Small enough for local inference, native to the stack the sibling ML apps use, language-conditioned so multi-object extends later | provisional |
| Action space | 2-vector in [-1, 1]: the controller's own axes | Human demos and policy output are the same signal in the same units; mixing to wheels happens after the policy | validated |
| Action mapping | Linear, no dead band | The dead band in the earlier draft existed only to model the real mBot's stall threshold. In sim it is pure harm: it put a hole in the action distribution that normalization statistics would be computed over. Throttle response is now smooth and monotonic down to 0.05 | validated |
| Observation | Overhead RGB frame only | Matches the eventual hardware exactly, and keeps the observation space trivial | validated |
| Goal representation | Painted on the floor, seen in the image | No extra observation channel, and it transfers to tape on a mat later | validated |
| No scoring in the loop | Nothing measures success automatically | SmolVLA is behaviour cloning: no reward in training, nothing consumed at inference. A scorer is worth building only to compare two trained policies | validated |
| Environment | uv + Python | Same runtime shape as the sibling apps | validated |

## Provisional assumptions and risks

| Assumption or risk | Impact | Cheapest validation | Authorized pivot |
|---|---|---|---|
| A flat-fronted diff-drive base can push a block without climbing it | Fatal to the task | **Validated** 2026-08-28: 0.52 m of forward push in 4 s, block stays at rest height, no lateral drift | Adjust pusher geometry, block mass, friction |
| SmolVLA's base checkpoint is pretrained largely on fixed-arm teleop, so a 2-DoF nonholonomic base is out of distribution | Fine-tune may underperform | Train and evaluate in sim | Fall back to ACT or Diffusion Policy on the identical dataset |
| A human can teleoperate the task well enough to produce learnable demonstrations | No usable dataset | Drive it and see | Slow the robot; enlarge the goal; simplify starting layouts |
| The goal is at a fixed position, so a policy could learn "drive right" without looking at it | Overstates what the policy learned | Randomize the goal and re-evaluate | Randomize goal position in the scene |
| A sim-trained policy would transfer to real hardware | Out of scope for now | Deferred | Treat sim as pretraining; fine-tune on real data later |

## Implementation path

1. **Simulated arena.** MuJoCo scene, gamepad teleoperation. **Done**: 15 tests
   pass; push, wall containment, settling, and seed-identical rendering verified.
2. **Record.** Gamepad demonstrations into LeRobot dataset format, randomized
   starts. **Pass bar:** a reloadable dataset.
3. **Train.** Fine-tune SmolVLA on a remote GPU; evaluate in sim. **Pass bar:**
   the policy reaches the goal more often than a do-nothing control. This is
   where the out-of-distribution risk resolves.
4. **Later, not now.** Real robot: firmware, link, camera, real demonstrations.

## Verified so far

MuJoCo determinism needed two specific things, both from the `mujoco` skill: a
static `xyaxes` camera rather than a tracking one, and a throwaway
reset-plus-render in the constructor to burn the renderer's non-reproducible
first cycle. With both, two env instances at the same seed produce
byte-identical frames.

Episodes settle for one simulated second after reset. Without it, contact
resolution moved bodies about 8 mm during the first second and then went
perfectly still - a transient, but one that would have put unexplained motion
into every recorded episode.

## Skill routing

`mujoco` for the sim scene, `lerobot` for dataset format and fine-tuning,
`runpod` for training compute, `testing` for the pass bar.

## Alternatives considered

**Gemini Robotics-ER 2 (rejected).** Publicly available in preview, but a
text-output embodied-reasoning model: it emits points, boxes, trajectories and
plans, not motor commands, and no Gemini model currently accepts fine-tuning
through the Gemini API.

**ACT / Diffusion Policy (retained as fallback).** The documented pivot if the
SmolVLA fine-tune disappoints. Same dataset, same harness.
