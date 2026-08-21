# VLA Pick and Place

A local robotics workspace for the SO-101 arm, built on the published
[SO101-Nexus](https://github.com/johnsutor/so101-nexus) MuJoCo environment.
Drive the arm yourself, joint by joint, and watch published expert
demonstrations of the same task in the same scene — side by side, on a laptop,
with no GPU.

```bash
git clone https://github.com/robium-ai/robium-apps
cd robium-apps/vla-pick-and-place
./app doctor
./app run
```

Then open <http://localhost:8765/ui>.

Runs natively on macOS (Apple Silicon) and Linux. No NVIDIA GPU, no Isaac Sim,
no ROS, no physical robot, no Hugging Face account.

## What it actually does

Two things, because two things are all that currently work:

**Drive the arm — live simulator.** Six sliders *are* the environment's action
space: absolute joint angles in radians, bounded by the real actuator limits.
The vector you dial in is the vector `step()` receives. The reward, grasp
flag, object-to-target distance and success shown under the cameras come
straight out of the simulator's `info` dict — this app computes none of them.

**Watch a demonstration — recorded.** An episode from
[`johnsutor/MuJoCoPickAndPlace-v1`](https://huggingface.co/datasets/johnsutor/MuJoCoPickAndPlace-v1),
pinned to a commit, replayed frame by frame. It is playback: no simulation
step runs, no policy is involved, and the page says so on every frame. Its
joint numbers are shown in the dataset's own units (degrees, gripper as
percent of travel) rather than silently converted, because they are not the
simulator's radians.

**There is no trained controller.** No lightweight ACT or SmolVLA checkpoint
has been trained against this pinned environment yet, and this app will not
substitute one trained somewhere else. `./app controllers` prints every
registered controller and the specific reason it cannot run here.

**There is a way to get one.** A Hub-wide survey found no dataset recorded in
this scene larger than ten episodes, so the app collects its own:

```bash
./app expert 30     # the scripted expert's success rate (79/100 over seeds 0..99)
./app record 400    # ~400 successful demonstrations -> outputs/dataset/
```

The expert drives the arm in TCP space so that **upstream solves the IK** — this
app owns no solver and no physics tweak — but records the joint targets the
environment derived, in radians at the real 50 Hz control rate. A recorded
episode replayed through the demo's own control mode reproduces the success, so
the data trains a controller this demo can actually run. See
`docs/training-guide.md`.

## Commands

| Command | What it does |
| --- | --- |
| `./app doctor` | Diagnose prerequisites and port conflicts |
| `./app build` | Install dependencies |
| `./app run` | Serve the workspace on `:8765` |
| `./app contract` | Print what the pinned environment actually is |
| `./app dataset-check` | Verify the pinned demonstrations match this environment |
| `./app controllers` | List controllers and why unavailable ones cannot run |
| `./app expert [N]` | Measure the scripted expert's success rate |
| `./app record [N]` | Record N successful expert demonstrations |
| `./app sim [SEED] [N]` | Drive the simulator headless, write an `.rrd` |
| `./app play [EPISODE]` | Replay a recorded demonstration headless, write an `.rrd` |
| `./app test` | Run the regression suite |
| `./app stop` | Free port 8765 if a crashed run still holds it |

`./app sim` and `./app play` write Rerun recordings under `outputs/viz/` with
both cameras, joint state, action and reward on one scrubbable timeline:

```bash
./app sim 3 60
uv run rerun outputs/viz/sim_seed3.rrd
```

The desktop Rerun viewer is the timeline surface. The web page renders frames
directly instead — see "Known limitations".

## The environment

Everything about the physics, the scene, the task and the success predicate
belongs to `so101-nexus`, pinned exactly:

| | |
| --- | --- |
| Package | `so101-nexus==0.5.1` |
| Environment | `MuJoCoPickAndPlace-v1` (MuJoCo backend) |
| Action space | `Box(6)`, absolute joint position in **radians** (`pd_joint_pos`) |
| Observation | 6-dim joint state, 43-dim privileged state, wrist + overhead cameras at 640×480 |
| Control rate | `control_dt = 0.02` s (50 Hz) |
| Episode cap | 1024 steps |
| Success | upstream's `info["success"]` — this app defines no predicate of its own |
| Throughput | ~60 env steps/s with both cameras on, measured on Apple Silicon |

`./app contract` re-measures all of it and fails loudly if the installed
package no longer matches. That check also runs at gateway boot, so a schema
drift stops the demo instead of quietly relabelling what you are looking at.

The app vendors no MJCF, no meshes and no scene. Earlier versions did — a
hand-built scene, a damped-least-squares IK solver, a calibrated grasp offset
and a bespoke success predicate — and all of it is gone.

## The demonstrations

Two published datasets exist for this task. They are **not** interchangeable,
and telling them apart needs more than a schema check:

| | `johnsutor/MuJoCoPickAndPlace-v1` | `ataghof/so101nexus-cube500-binary` |
| --- | --- | --- |
| Role | **primary** — what the page plays | registered second candidate |
| Episodes | 10 | 500 |
| Cameras | `wrist`, `overhead` | `cam0`, `cam1` |
| Schema check | pass | pass |
| Scene check | **pass** (0.002 from a live render) | **fail** — no identifiable static view |
| Extras | ships `meta/so101_nexus_env.json`, reward + success channels | published collector and a trained model |

The second dataset is larger and better training material, and it is
registered for exactly that reason. But its recorded frames are not this
environment's: wood-textured ground, an orange robot, and an angled side view
where so101-nexus's overhead camera is top-down. Its collector must have
overridden the scene config, and its `cam0`/`cam1` names carry no view
identity, so neither camera can even be mapped onto this environment's. Using
it means reproducing its scene configuration first.

`./app dataset-check` runs both checks and prints the numbers.

## Known limitations

- **No trained controller.** Stated plainly above and by `./app controllers`.
  `docs/training-guide.md` is the path to one.
- **The page does not embed Rerun.** It used to, and the embedded viewer
  rendered a black canvas: the recording bytes are a valid RRF2 stream, the
  media-stream chunks are fetched with 200s, the viewer reports ready and
  wgpu initialises, and nothing errors — the canvas is simply black.
  Shipping that would mean shipping a demo whose main surface shows nothing,
  so the page renders frames directly and Rerun stays the offline surface,
  where it works.
- **One visitor at a time.** A second session can take the instance over; a
  hosted version would need liveness-based claims.
- **Ten demonstration episodes** in the playback dataset. It is a reference and
  a playback source; `./app record` is where training data comes from.
- **The expert misses ~21% of seeds.** Failures are discarded rather than
  recorded, so this costs collection time, not data quality.

## Docs

- `docs/architecture-brief.md` — the stack, the measurements, the decisions
- `docs/training-guide.md` — how to train the missing ACT baseline
