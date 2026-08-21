# Architecture brief — vla-pick-and-place

**Last verified:** 2026-08-17 on macOS 26.5 / arm64 / Python 3.12.13 /
mujoco 3.10.0 / gymnasium 1.3.0 / lerobot 0.6.0 / so101-nexus 0.5.1.

## What this app is

A local workspace for the SO-101 arm on the published SO101-Nexus MuJoCo
environment. A visitor can drive the arm by hand and watch published expert
demonstrations of the same task in the same scene. It runs natively on Apple
Silicon and Linux with no GPU.

It is deliberately not a trained-policy demo. There is no checkpoint that
matches this environment yet, and the app says so rather than shipping one
that does not.

## The decision that shaped everything

The app used to own its physics: a hand-written MJCF scene built on vendored
menagerie meshes, a damped-least-squares IK solver, a brute-force-calibrated
grasp offset, and a five-condition success predicate with a settle debounce.
That stack worked, and it was the reason nothing else could be reused — no
published dataset and no published checkpoint had ever seen that scene, so the
one SmolVLA checkpoint trained for it scored 0% and nothing else could be
plugged in at all.

`so101-nexus` now publishes what was missing: the same robot in the same
simulator, installable from PyPI, with golden-trajectory regression tests, a
documented stability contract, LeRobot-compatible recording, and published
datasets recorded in it. So the app stopped simulating and started
translating. Everything below follows from that.

## Stack

| Layer | Choice | Why |
| --- | --- | --- |
| Environment | `so101-nexus==0.5.1`, `MuJoCoPickAndPlace-v1` | Published, pinned, tested upstream; the only SO-101 MuJoCo layer with matching public datasets |
| Simulator | MuJoCo 3.10 (upstream's backend) | Native on macOS and Linux; the local-first promise depends on it |
| Backend | MuJoCo, not Warp | Warp needs CUDA. Optional upstream, deliberately unused |
| Data (playback) | LeRobot v3 datasets from the Hub, pinned to commit shas | Verified against a live render before use |
| Data (training) | Recorded here by a scripted expert, in this exact scene | No published dataset larger than 10 episodes exists for the stock scene |
| Web | FastAPI gateway + Gradio workspace on `:8765` | Same session contract as `robot-navigation`, so the shared orchestrator reuses unchanged |
| Visualization | Direct frame rendering in-page; Rerun `.rrd` offline | See "Rerun" below |
| Env manager | `uv` + Python 3.12 | Pure-Python stack, no ROS, no system deps |

## Measured environment contract

Captured by `python -m vla_pick_and_place.run contract`, asserted by
`tests/test_app.py`, and re-checked at gateway boot.

```
env_id                     MuJoCoPickAndPlace-v1
max_episode_steps          1024
control_dt                 0.02 s (50 Hz)
action                     Box(6) float32, absolute joint position, RADIANS
observation.state          (6,)      joint positions
observation.environment_state (43,)  privileged state, 10 components
observation.images.wrist   (480, 640, 3) uint8
observation.images.overhead(480, 640, 3) uint8
success key                info["success"]
```

Additional facts established by measurement, not assumption:

- **Deterministic resets.** A fixed seed reproduces the observation *and* the
  rendered frame exactly; a different seed does not.
- **Throughput.** ~60 env steps/s with both camera observations active,
  measured at 256×256, 320×240 and 640×480 — within noise of each other. The
  per-render fixed cost dominates, so the smaller sizes buy nothing and lose
  the dataset match. 640×480 it is.
- **Camera randomization.** The wrist camera's FOV, pitch and mount offset are
  randomized per reset by design. Only the static overhead view is usable as a
  scene-identity probe.
- **Reset noise.** `robot_init_qpos_noise` means a reset joint *position* can
  settle marginally outside the actuator *control* range — the gripper comes
  back at −0.17454 against a −0.17453 bound. Anything binding joint state to a
  bounded widget must clamp.
- **Dataset fps is not control rate.** Upstream is explicit that a recorder
  sleeps to pace an operator but advances the simulation exactly one step per
  recorded frame. So one dataset frame is one env step, and the datasets' 30 /
  33 fps figures are playback rates, not a control-rate mismatch.

## Data source: why the smaller dataset won

Two published datasets exist for `MuJoCoPickAndPlace-v1`. Both load cleanly
under LeRobot 0.6.0, both have 6-dim state and action, both record the same
task string, both have two 480×640 cameras. **A schema check cannot tell them
apart.**

Rendering a frame from each next to a fresh render from the pinned environment
can:

| | `johnsutor/MuJoCoPickAndPlace-v1` | `ataghof/so101nexus-cube500-binary` |
| --- | --- | --- |
| Pinned revision | `8e295eba` | `bdd2d23b` |
| Episodes / frames | 10 / 4,725 | 500 / 20,647 |
| Camera names | `wrist`, `overhead` | `cam0`, `cam1` |
| Ground | grey, matches | wood texture |
| Robot colour | yellow, matches | orange |
| Static view | top-down overhead, matches | angled side view |
| Overhead colour distance from a live render | **0.0023** | not comparable |
| Env provenance | ships `meta/so101_nexus_env.json` | none |
| Reward / success channels | yes | no |
| Gripper actions | continuous | binary {0, 45} |

The `ataghof` collector clearly overrode the scene configuration. Its dataset
is the better *training* material — 500 episodes, a published collector, and a
trained MolmoAct2 checkpoint — and it stays registered for that reason. It is
not a stand-in for this environment's demonstrations, and playback and
evaluation must not point at it until its scene config is reproduced.

`SCENE_COLOR_TOLERANCE` is 0.05, checked on the overhead view only. The
matching dataset sits 20× inside it; the test asserts the *margin*, not just
the threshold, so a scene change surfaces before the threshold stops working.

## Units: the trap

LeRobot dataset rows are **not** simulator units. Body joints are recorded in
degrees and the gripper as a percent of jaw travel; the environment's action
space is radians. A whole-vector `np.deg2rad` silently corrupts the gripper
channel. `so101-nexus` publishes the correct converters
(`dataset_row_to_sim_qpos` and its inverse) and this app uses them — nothing
here hand-rolls the conversion. The UI shows recorded numbers in the dataset's
own units and labels them, rather than converting behind the visitor's back.

## Controller compatibility

`policy/controllers.py` makes compatibility a declared, checked property
rather than something discovered by watching an arm flail. Each controller
records repo and pinned revision, policy family and LeRobot version,
observation and action schema, camera names and resolution, control rate and
horizon, device and memory, the environment it was trained against, and both
published and locally reproduced evaluation results.

Two rules it enforces:

- **Nothing falls back.** A selected controller that fails its check raises
  with the mismatched field named. It never degrades into dataset playback or
  a scripted motion, because a viewer cannot tell those apart by looking.
- **Unproven is unavailable.** "A published evaluation exists" is not a local
  check.

Currently registered, both unavailable:

- **`ataghof/molmoact2-so101nexus-lora-champion`** — blocked twice over. It
  was trained on the mismatched dataset, so its observations would not match
  these frames (`check_against_env` reports the camera-key and action-unit
  mismatches concretely). And it is a ~6B model its authors evaluated on a
  24 GB CUDA GPU; no Apple Silicon measurement of it exists here. Its
  published result — 93% grasp, 50% loose placement, 30% strict placement over
  30 held-out cube positions — is recorded as *their* number in *their* scene.
- **`zwan1003/pickplace_skills_vla_v3_2_ckpt060k`** — the closest published
  policy to this environment, and still a fork away. Trained on a **two-disc**
  subclass where a green and a blue target are both always visible and the
  instruction alone identifies the goal; this scene has one disc, so the
  distinction the policy exists to make is absent. Measured 0.091 overhead
  colour distance against a 0.05 tolerance. It also targets so101-nexus 0.3.12
  (its code imports the `so101_nexus_core` / `so101_nexus_mujoco` split
  packages 0.5.1 no longer has) and LeRobot 0.4.4, and needs its authors'
  contact hardening at evaluation. Worth knowing it exists: 33% grasp / 97%
  placement / 37% whole task, with an ablation showing it follows language
  rather than colour.
- **Local ACT baseline** — not trained yet. Its declared schema already
  matches this environment; only the checkpoint is missing.

A Hub-wide survey on 2026-08-17 (metadata, dataset filters, full-text) plus the
upstream repo found exactly **two** published policies touching so101-nexus —
the two above — and **no checkpoints at all** from the upstream maintainer, who
ships environments, datasets and BC/PPO training scripts only. There is no
trained controller for the stock scene anywhere.

## Threading

MuJoCo's GL context is thread-affine, CGL on macOS especially: an environment
built on one thread and rendered from another deadlocks in `make_current`,
forever, with no exception. This app has hit that for real.

Gradio runs each request on whatever worker is free, so a shared env is a
guaranteed hang — and a per-request env would throw away the arm pose between
clicks, which makes driving the arm by hand impossible. `demo/session.py`
therefore gives the environment **one owner thread for its whole life** and
posts commands to it over a queue. Construction, every step, every render and
`close()` happen there. `tests/test_app.py` drives the worker from a
different thread on purpose.

## Rerun

The page does not embed Rerun. It did, and the embedded viewer rendered a
black canvas. Measured rather than guessed:

- the recording bytes are a valid RRF2 stream (85 KB carrying real image data,
  readable off disk),
- Gradio's media-stream chunks are fetched by the browser with 200s,
- `gradio_rerun` logs "Rerun viewer ready" and "Adding new log receiver",
- wgpu initialises and the canvas is correctly sized (2160×1404 backing),
- no error appears in the console,
- and the canvas is black — through both an initial `value=` and a
  `blocks.load` stream.

Shipping that means shipping a demo whose main surface shows nothing, so the
page renders frames directly. Rerun remains the offline surface and works
there: `./app sim` and `./app play` write `.rrd` files that open correctly in
the desktop viewer, which is where scrubbing a timeline belongs anyway.

## Layout hazard worth recording

Gradio's `.row`/`.column` classes carry `flex-wrap: wrap`, and every container
in the workspace shell is one of them. In a column-direction box that means a
child which does not fit starts a **new column to the right**, off screen. The
panel renders at full size, reports `visibility: visible`, and is nowhere
anyone can see it; `overflow-y: auto` never engages because nothing overflows
vertically. It fails silently and differently per viewport, which is how it
survived — a rail with few enough short sections fits in one column and the
bug is invisible. `dashboard.css` now forces `flex-wrap: nowrap` on every
container in the shell, and `tests/test_app.py` asserts it per selector.

## Test pyramid

Deliberately small: 14 tests in two files, and the default run is 10 tests in
~2.5 s. Only failures that have actually happened here, or that would ship
something false, earn a test — a suite slow enough to skip is worse than no
suite. Everything else was cut.

| What it guards | File | Default run |
| --- | --- | --- |
| Pins agree with config; revisions are shas | `test_app.py` | yes |
| The live env still matches the recorded contract, frames not black | `test_app.py` | yes |
| The arm is drivable from another thread, and the command is not rewritten | `test_app.py` | yes |
| No controller is available and each says why | `test_app.py` | yes |
| The page names its source and units; playback is never called a policy | `test_app.py` | yes |
| No shell container may wrap; reset state is clamped to slider bounds | `test_app.py` | yes |
| Pinned demonstrations match schema **and** scene | `test_app.py` | `-m slow` |
| Gateway boots, guards sessions, returns real frames, shuts down | `test_demo.py` | `-m slow` |

The gateway smoke asserts pixels and labels, not just status codes: a returned
camera frame must not be black or flat, and a recorded episode must announce
itself as a recording. "The endpoint answered 200" was true of the version
whose viewer showed nothing.

Verified 2026-08-17 from a clean checkout with an empty `HF_HOME`: `./app
doctor`, `./app build`, `./app contract`, `./app dataset-check`, `./app test`
(10 passed in 2.4 s), `make demo-smoke` (3 passed), `./app sim`, `./app play`.
Full suite including slow: 14 passed in ~11 s.

## Known limitations

- No trained controller matches this environment.
- The primary dataset is 10 episodes — a reference and a playback source, not
  a training set.
- One visitor at a time; a second session can take the instance over.
- The embedded-Rerun path is unresolved upstream, not worked around.

## Collecting training data

The survey found no dataset recorded in the stock scene larger than ten
episodes, so the app generates its own: `./app record N` runs a scripted
expert and keeps only the episodes upstream scores as successful.

The expert is thin by construction. The environment is built in `pd_ee_pose`
control mode, so an action is a TCP pose and **upstream solves the IK** — this
app inverts no Jacobian, owns no scene, and does not touch the contact model.
What is left is a waypoint sequence and four measured constants.

`GRASP_Z` is the load-bearing one, and its sensitivity is the reason the first
attempt scored 13%. The jaws pinch ~9 mm below the TCP site (measured from
MuJoCo contact positions, std 2.6 mm over seeds), so the TCP must be commanded
low. Grasp-then-lift survival over 12 seeds:

| TCP height above cube centre | survives |
| --- | --- |
| 0.006 m | **100%** |
| 0.009 m | 83% |
| 0.012 m | 33% |
| 0.016 m | 0% |

Two more findings worth keeping: commanding the gripper fully closed on a
25 mm cube *extrudes* it (at -0.174 rad a slower carry scored worse than a
fast one — 0/12 vs 3/12), and a 108 mm setpoint jump forms a grasp then pops
it, so motion is interpolated. End to end the expert clears **79/100 seeds**.

The recorded data is in simulator radians at fps 50 (the real control rate),
and the expert records the JOINT targets the env derived rather than the TCP
poses it sent — so a recorded episode replayed through the demo's own
`pd_joint_pos` env reproduces the success. That equivalence is a test, not a
claim.

## Next

The follow-up training block, deliberately separate: train ACT on a pinned
SO101-Nexus dataset, evaluate it in this exact environment over a fixed seed
set, publish it with full processor files and environment/dataset revisions,
and only then make it the local trained-controller option. SmolVLA follows
once ACT is credible. See `docs/training-guide.md`.
