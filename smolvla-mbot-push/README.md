# SmolVLA mBot Push

A differential-drive robot pushes a block to a goal in MuJoCo, seen only through
a fixed overhead camera. The plan is to record demonstrations with a game
controller and fine-tune a SmolVLA policy to reproduce them.

Everything runs in simulation. It installs in seconds and needs no GPU.

## Quick start

```bash
./app build    # create the uv environment
./app check    # headless: step and render the arena
./app drive    # drive it yourself
```

`./app drive` opens the overhead view and lets you drive:

| | |
| --- | --- |
| **Throttle** | up / down arrow, or `W` / `S` |
| **Steer** | left / right arrow, or `A` / `D` |
| **Reset layout** | `R` |
| **Quit** | `Q` |

A game controller is used automatically when one is attached, with the left
stick as throttle and the right stick as steer. Held keys ramp toward full
deflection rather than snapping to it, because square-wave demonstrations are
poor material to clone.

What you see and what you press are exactly what the policy will later consume
and produce.

## The pipeline

Every step below has been exercised end to end; only the episode contents are
yours to supply.

**1. Record a handful of episodes.**

```bash
./app record --repo-id <you>/mbot-push-sim --episodes 5 --push-to-hub
```

Space starts and stops an episode, `r` discards one that went badly, `q` quits.
Five episodes is not enough to learn from - it is enough to prove the pipeline
end to end before spending time collecting properly.

**2. Fine-tune on Hugging Face Jobs.**

```bash
uv run lerobot-train \
  --dataset.repo_id=<you>/mbot-push-sim \
  --policy.path=lerobot/smolvla_base \
  --rename_map='{"observation.images.overhead": "observation.images.camera1"}' \
  --policy.repo_id=<you>/smolvla-mbot-push \
  --policy.device=cuda \
  --batch_size=8 --steps=2000 \
  --save_checkpoint_to_hub=true \
  --wandb.enable=false \
  --job.target=l40sx1 --job.timeout=2h --job.detach=true \
  --output_dir=outputs/train/smolvla
```

`--rename_map` is not optional. `lerobot/smolvla_base` expects three cameras
named `camera1`/`camera2`/`camera3`; this arena has one, and without the rename
the feature layouts do not line up. The 2-dim state needs no such treatment -
SmolVLA pads state internally up to `max_state_dim`.

Omit `--job.target` to run locally, but see the warning below first. List
hardware and pricing with `hf jobs hardware`.

**3. Drive the trained checkpoint.**

```bash
./app rollout --policy <you>/smolvla-mbot-push --repo-id <you>/mbot-push-sim
```

## Do not train a VLA on your Mac

`--policy.device=mps` is accepted and the run starts, which makes this an easy
mistake. A measured SmolVLA fine-tune on MPS managed 20 steps in two hours: a
real run would take weeks. MPS is fine for inference and for proving the loop
starts, which is exactly what `./app rollout` uses it for.

## How it works

The policy sees one thing and emits one thing:

- **Observation:** the overhead RGB frame. Nothing else - no positions, no
  headings, no state.
- **Action:** `(throttle, steer)`, each in `[-1, 1]` - your controller's own
  sticks.

`config.mix` turns those two numbers into wheel speeds, *after* the policy.
It rescales rather than clips when the mix overflows, so hard-forward
hard-turn keeps its curvature instead of flattening into a straight line.

The goal is painted on the floor rather than supplied as state, so the policy
sees it in the image and needs no extra input channel.

## The arena

A 1.0 x 0.8 m walled pen. Each reset randomizes the robot's pose and the block's
pose, then settles the physics for one simulated second before the episode
starts - contact resolution otherwise nudges bodies several millimetres, and
motion no action explains is exactly what confuses behaviour cloning.

Rendering is deterministic: two runs at the same seed produce byte-identical
frames. That needs a static camera (a tracking one re-runs its smoothing filter
per render) and a throwaway render at construction to burn the renderer's
non-reproducible first cycle.

## Command surface

| Command | What it does |
| --- | --- |
| `./app build` | Create the uv environment |
| `./app check` | Headless step-and-render self-check |
| `./app drive` | Drive the arena (keyboard, or controller if attached) |
| `./app record` | Record teleoperated episodes into a LeRobotDataset |
| `./app rollout` | Run a trained checkpoint in the arena |
| `./app smoke` | Run the test suite |

## Troubleshooting

**The controller does nothing.** Stick axis numbering varies by controller and
platform. Adjust the axis indices in `ui.py`. Unplug it to fall back to the
keyboard.

**Rendering fails on Linux.** The environment sets `MUJOCO_GL=cgl` only on
macOS, where it is the sole headless backend. On Linux set `MUJOCO_GL=egl`
(or `osmesa`) yourself.

## Status

Early but wired end to end: arena, teleoperation, recording, fine-tuning, and
rollout have each been run. What has *not* happened is a real training run on
real recorded episodes, so no claim is made that the policy works. See
[docs/architecture-brief.md](docs/architecture-brief.md) for the plan and the
open risks.

## Cleanup

```bash
make clean
```
