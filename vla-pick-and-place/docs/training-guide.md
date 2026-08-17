# Train your own SmolVLA policy

The checkpoint this app ships is a **100-step pipe-test** — near-identical to
the base model, and it scores 0%. That is the correct result for 100 steps,
not a bug. This guide is how you get one that actually picks and places.

Everything here is the path we ran ourselves, including the parts that cost us
money for nothing. Read the traps section before you submit anything billable.

**Budget:** ~$20-40 and ~4 hours of GPU time for the real run. Every step
before it is free.

---

## Step 0 — Prove the scene works locally (free, ~2 min)

```bash
./app doctor
./app oracle
```

`./app oracle` must print `oracle: 10/10 succeeded`. This is a scripted
inverse-kinematics controller using ground-truth state — no learning involved.
It is the canary for the scene, the physics, and the success predicate.

**If it is not 10/10, stop.** Nothing downstream can work: your dataset would
record failures and your policy would learn them. The oracle is the only thing
in this repo that tells you the *environment* is sound, independent of any
policy question.

---

## Step 1 — Get a dataset

You have two options.

### Reuse ours (free, instant)

`robium/so101_pick_cube` — 75 clean episodes, randomized cube spawns, recorded
by the oracle with failed episodes discarded and re-rolled. It is private; ask
for access, or record your own.

This is already the default (`DATASET_REPO_ID` in `config.py`), so if you use
it there is nothing to do here.

### Record your own (free, ~30-60 min of compute)

```bash
./app oracle          # confirm 10/10 first
make record           # oracle x75, failures discarded and re-rolled
```

`make record` writes a `LeRobotDataset` locally and **does not push**. That
separation is deliberate: look at what you recorded before it becomes the
thing your policy imitates. `make spot-check` logs episodes to Rerun so you
can scrub them.

When you are satisfied:

```bash
make push-dataset     # private by default
```

Set `HF_USER` to control the namespace (defaults to `robium`). Point
`DATASET_REPO_ID` at your repo if you changed it.

> **macOS video encoding.** `record()` passes `vcodec="auto"` on purpose.
> LeRobot's default SVT-AV1 encoder intermittently crashes at teardown on
> macOS and kills the whole run as `BrokenProcessPool` — a 75-episode
> recording died at episode 60 that way. `auto` selects hardware
> VideoToolbox. Do not "simplify" this back to the default.

---

## Step 2 — The free gate (free, ~2 min, do not skip)

```bash
make train-smoke
```

Five training steps on your CPU. It is not training and it is not meant to be
— it proves the training loop *assembles*: config parses, tensor shapes line
up, the camera rename resolves, the dataset loads, a checkpoint writes.

**Run this before every paid submission.** It has already caught one real
config bug for free. A shape error found here costs two minutes; the same
error found on HF Jobs costs a full billed run and produces no artifact.

It needs Hub access (it pulls the base model and your dataset).

---

## Step 3 — The pipe test (~$1-2, ~10 min)

```bash
make train
```

Submits a deliberately under-trained 100-step fine-tune to HF Jobs. Its job is
to prove the *remote* loop end-to-end — submit, train, save, push to Hub, pull
back, evaluate — not to produce a working policy. Expect ~0% at eval. That is
the pass condition here.

Skip this only if you have run it before on the same config.

---

## Step 4 — The real run (~$20-40, ~4 h)

```bash
make train-full
```

20,000 steps, batch 64, on `a10g-small`. The reference run scored **60-80%**
success. `SUCCESS_RATE_FLOOR` is set to 0.60 — the bottom of that band, which
is honest without being flaky.

**Read the job log for the checkpoint id.** See trap #1 below; this is not
optional.

---

## Step 5 — Score it, then wire it in

```bash
./app eval <your-checkpoint-id-or-path>
```

Rolls the checkpoint out over seeded episodes and writes a numeric success
rate to `outputs/eval/*/eval_info.json`. Exits non-zero below the 60% floor —
it is a pass bar, not a report.

To make the demo page use it:

```bash
VLA_DEMO_CHECKPOINT=<your-checkpoint-id> ./app run
```

or, permanently, set `DEMO_CHECKPOINT` in `src/vla_pick_and_place/config.py`.
That one constant is the whole handoff between "trained a policy" and "the
demo runs it".

---

## Traps that cost us real money

These are the ones that produce a *plausible-looking* failure. The full list
is in `docs/architecture-brief.md`.

**1. HF Jobs ignores `--policy.repo_id`, and pushes to your personal
namespace.** You ask for `robium/smolvla_so101_pick`; it publishes to
`<your-username>/train_<timestamp>`. The only way to learn the real id is the
`Model pushed to <url>` line in the job log. We once recorded the right
timestamp under the wrong namespace, and every trained-controller run 404'd
for two weeks while looking like a perfectly reasonable repo id. Copy the id
from the log; never retype it.

**2. `--output_dir` is passed verbatim to the remote container.** Hand it a
local macOS path and the job trains all the way to completion and *then*
crashes at checkpoint save with `PermissionError: '/Users'` — a full paid run
for zero artifact. `REMOTE_OUTPUT_DIR` is a `/tmp/...` container path for
exactly this reason.

**3. A repo that exists is not a checkpoint that loads.** A job that dies
between writing its config and pushing its weights leaves a real, listable Hub
repo containing only `train_config.json`. We have one. `policy/resolve.py`
checks for `model.safetensors` and fails with a message that says so.

**4. HF Jobs needs prepaid credits, separately from being logged in.** A
correctly-formed submission fails with `402 Payment Required` if the account
has none. This is genuinely useful: it validates auth, dataset availability,
and command shape for free, because a rejected job never bills.

**5. Never train on macOS.** MPS fine-tuning runs about two hours per twenty
steps; CPU is worse. Local hardware is for inference and eval only, where
SmolVLA is fast (~0.55 s/forward-pass on Apple Silicon, ~17x faster than CPU
on the same machine).

**6. Camera renaming is required at train *and* eval.** SmolVLA's base
checkpoint expects three cameras named `observation.images.camera1/2/3`; this
env has two. Training passes `--rename_map` plus `--policy.empty_cameras=1`
for a masked placeholder. At eval you feed the env's raw `wrist`/`scene` keys
and let the checkpoint's own saved `policy_preprocessor.json` do the rename —
renaming yourself first breaks it. Both sides are already wired; the trap is
"fixing" one of them.

---

## Reference

| Knob | Where | Default |
| --- | --- | --- |
| Dataset | `DATASET_REPO_ID` | `robium/so101_pick_cube` |
| Hub namespace | `HF_USER` env | `robium` |
| Full-run steps | `TRAIN_STEPS` | 20,000 |
| Full-run batch | `TRAIN_BATCH_SIZE` | 64 |
| GPU target | `TRAIN_JOB_TARGET` | `a10g-small` |
| Pass bar | `SUCCESS_RATE_FLOOR` | 0.60 |
| Demo's checkpoint | `DEMO_CHECKPOINT` / `VLA_DEMO_CHECKPOINT` | the 100-step pipe test |

`src/vla_pick_and_place/config.py` is the single source of truth for every run
parameter — the Makefile and the tests both build their invocations from it,
so a hand-run stage and the pass-bar test cannot drift apart.
