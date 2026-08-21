# Training guide — the missing local controller

This app ships no trained controller. This is the path to one.

The order matters and it is not the obvious one: **ACT first, SmolVLA second,
and neither before a free local pipeline smoke.** A previous version of this
app skipped straight to fine-tuning a 450M VLA against a hand-built scene, and
the result scored 0% for reasons that had nothing to do with training — the
scene, the dataset and the checkpoint had no published contract binding them
together. Everything below exists to prevent a repeat.

## The contract a checkpoint must satisfy

Anything claiming to drive this environment has to match it on every one of
these. `./app contract` prints the current values; `./app controllers` shows
each registered controller checked against them.

| Field | Value |
| --- | --- |
| Environment | `MuJoCoPickAndPlace-v1`, `so101-nexus==0.5.1` |
| Action | `Box(6)` float32, absolute joint position, **radians** |
| State | `observation.state`, 6-dim |
| Cameras | `observation.images.wrist`, `observation.images.overhead`, 480×640 |
| Control rate | 0.02 s (50 Hz) |
| Success | upstream `info["success"]` |

A checkpoint that matches five of six is not "close" — it is incompatible, and
`policy/controllers.py` will refuse it with the mismatched field named rather
than run it and disappoint.

## Step 0 — the data problem is solved: collect it here

**`./app record 400`.** This app now generates its own demonstrations, in the
exact pinned environment the demo runs, with a scripted expert
(`src/vla_pick_and_place/data/expert.py`).

That is not the obvious choice, so here is why it beats every published
alternative. A Hub-wide survey (see below) found no dataset recorded in the
stock `MuJoCoPickAndPlace-v1` scene larger than ten episodes:

| Dataset | Size | Why it is not the answer |
| --- | --- | --- |
| `johnsutor/MuJoCoPickAndPlace-v1` | 10 eps | Right scene, right provenance — but ten episodes is a reference, not a training set |
| `ataghof/so101nexus-cube500-binary` | 500 eps | Wood ground, orange robot, angled side view: a different scene |
| `zwan1003/pickplace_skills_v3_2` | 380 eps | Two-disc subclass, so101-nexus 0.3.12, hardened contacts: a different world |

Training on someone else's scene is exactly what produced the 0%-success
checkpoint this app used to ship.

### What the recorder produces

- **Simulator units.** `observation.state` and `action` are joint angles in
  RADIANS — the environment's own action space. No degree/percent conversion
  at any boundary, and no gripper channel to corrupt.
- **fps 50 = the real control rate.** `control_dt` is 0.02 s and one recorded
  frame is one env step, so the fps here is the truth, not a playback
  convention.
- **Successes only.** An episode is written only if `info["success"]` holds.
  The expert clears **79/100 seeds**; failures cost collection time, not data
  quality.
- **Executable by this app.** The expert drives in TCP space so that upstream
  solves the IK, but records the JOINT targets the environment derived. A
  recorded episode replayed through the demo's own `pd_joint_pos` env
  reproduces the success — asserted by
  `tests/test_app.py::test_expert_records_data_this_environment_can_execute`.

### What it does not do

It does not touch the physics. Other projects on this simulator harden the
contact model to make the grasp easier; that would make the recording describe
a world the demo does not run in. The stock contact model is what the expert
works within, which is why the four constants in `expert.py` are as sensitive
as they are — `GRASP_Z` alone moves grasp survival from 100% to 0% across six
millimetres.

```bash
./app expert 30     # the expert's own pass bar: success rate over seeds 0..29
./app record 400    # ~400 successful episodes into outputs/dataset/
```

Nothing pushes to the Hub. Review the dataset before you do.

## Step 1 — free local pipeline smoke

Before any paid run, prove the loop assembles: config, shapes, dtypes,
normalization statistics. A handful of steps on CPU is enough and costs
nothing. Catching a shape error here instead of ten minutes into a billed job
is the entire point.

Confirm before the smoke:

- the dataset loads at its pinned revision under LeRobot 0.6.0,
- its camera keys map onto `observation.images.wrist` / `.overhead`,
- its action rows are in the units you think they are (`./app dataset-check`
  reports this; recorded rows are degrees plus gripper percent, **not**
  radians),
- and `./app contract` passes.

## Step 2 — ACT, not SmolVLA

ACT is the right first baseline here:

- it is small enough to train quickly and to run on CPU or MPS afterwards,
  which is the whole local promise of this app;
- it is not language-conditioned, so nothing about the result can be
  misrepresented as instruction-following;
- and a credible ACT number is the only honest basis for claiming a later
  SmolVLA fine-tune improved anything.

Train it against the pinned dataset. Record the dataset revision, the
environment revision, the seed and the exact command alongside the weights.

## Step 3 — evaluate in *this* environment

Not a similar one. Fixed seeds, enough episodes for the threshold you intend
to state, and upstream's `info["success"]` as the predicate — never a
re-derived one.

Report the number with its conditions attached: which environment revision,
which dataset revision, how many episodes, which seeds. The published
MolmoAct2 result (93% grasp / 50% loose placement / 30% strict placement over
30 held-out positions) is a good model of what to state, and a reminder that
"success" has more than one definition — say which you used.

## Step 4 — publish it properly

A checkpoint is not usable by this app unless it ships:

- the model weights **and** the processor / normalization files,
- the environment id and pinned `so101-nexus` version it was trained against,
- the dataset repo id and pinned revision,
- the evaluation protocol and result.

A repo containing only `train_config.json` is what a job that died before
pushing weights leaves behind. It resolves fine and loads nothing.

## Step 5 — register it

Add a `Controller` entry in `src/vla_pick_and_place/policy/controllers.py`
with every field populated, including `local_eval` — the result *you*
reproduced on this machine, not the one on the model card. Set
`available=True` only after that check has actually run.

`tests/test_app.py::test_no_controller_is_available_and_each_says_why`
asserts the current empty state on purpose. Making it fail is how a real
controller arrives, and updating it should be a deliberate act.

## Step 6 — SmolVLA, afterwards

Only once ACT clears an agreed bar. Fine-tune on the same contract, on a
remote GPU, and compare the three results without implying that different
metrics or different environments are equivalent.

## What not to do

- Do not point this app at a checkpoint trained in another environment.
  `gpudad/act_so101_chunk40_250k_v1` (different env id, 4-D end-effector-delta
  actions, 10-D state), `davidlinjiahao/lerobot_so101_base_sim_pickplace`
  (12-D state with privileged cube/bin information, three evaluation
  episodes), and `szk1ck/so101-pickplace-sim-mujoco` (no published simulator
  source or reproducible evaluation contract) are all near-misses that would
  load and then behave like noise.
- Do not let a failed controller fall back to dataset playback or a scripted
  motion. A viewer cannot tell them apart.
- Do not advertise the MolmoAct2 checkpoint as a local Mac controller without
  a measured local test. It is ~6B parameters, evaluated on a 24 GB GPU.
- Do not load `zwan1003/pickplace_skills_vla_v3_2_ckpt060k` against this
  environment. It is the closest published policy and still needs their fork:
  their two-disc scene, their so101-nexus 0.3.x split packages, their LeRobot
  0.4.4, and their hardened contacts. `./app controllers` states all of it.

## The survey behind that decision

Searched 2026-08-17 across the Hugging Face Hub (metadata, dataset filters and
full-text) and the upstream GitHub repo. The complete set of published policies
touching so101-nexus is **two**, and neither runs here:

| Policy | Blocker |
| --- | --- |
| `ataghof/molmoact2-so101nexus-lora-champion` | Different scene (wood ground, orange robot, side view); ~6B params on a 24 GB CUDA GPU |
| `zwan1003/pickplace_skills_vla_v3_2_ckpt060k` | Two-disc scene subclass; so101-nexus 0.3.12 + LeRobot 0.4.4; custom hardened physics |

The upstream maintainer publishes **no checkpoints at all** — only the
environments, two datasets, and BC/PPO training scripts under `examples/`
(mostly Warp/CUDA). `johnsutor/so101-nexus-envs` is a LeRobot EnvHub shim, not
a policy.

So the gap this guide exists to close is real: there is no trained controller
for the stock `MuJoCoPickAndPlace-v1` scene anywhere, from anyone.
