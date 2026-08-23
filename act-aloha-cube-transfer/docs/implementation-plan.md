# ACT ALOHA Cube Transfer Implementation Plan

**Date:** 2026-08-23
**Source design:** `docs/architecture-brief.md`
**Status:** complete — locally verified; production deployment intentionally pending

## Objective

Build a reference application around the pinned official LeRobot ACT ALOHA
Transfer Cube checkpoint. The finished app must run locally on Apple Silicon,
pass real-policy smoke tests, expose the standard `./app` operator interface,
provide a live Gradio and Rerun workspace, and pass a production-shaped CPU
container gate before any hosted-demo integration is published.

The plan deliberately proves checkpoint migration, simulator compatibility,
and real policy behavior before building the full UI.

## Scope boundaries

In scope:

- official ACT Transfer Cube checkpoint at the pinned revision;
- official `AlohaTransferCube-v0` simulation;
- native MPS and CPU inference;
- execution horizons 25, 50, and 100 from a 100-action prediction;
- deterministic seeds, replay, randomization, cancellation, evidence, Rerun;
- CPU container and local website lifecycle integration after the app passes;
- README, architecture updates, registry card, and app metadata.

Out of scope:

- ALOHA Insertion;
- training or fine-tuning;
- real ALOHA hardware;
- community checkpoints or checkpoint comparison;
- production deployment without a separate explicit request.

## Phase 1: Bootstrap the reference-app contract

### Files

- `.python-version`
- `.gitignore`
- `pyproject.toml`
- `uv.lock`
- `Makefile`
- `app`
- `robium-app.yaml`
- `README.md`
- `src/act_aloha_cube_transfer/__init__.py`
- `src/act_aloha_cube_transfer/config.py`
- `tests/test_app_cli.sh`

### Work

1. Copy only the proven structural patterns from `diffusion-policy-pusht`:
   src layout, uv packaging, six launcher verbs, process/log locations, test
   grouping, and Make target naming.
2. Rename every package, image, port-label, process name, and health string for
   ACT ALOHA; do not retain PushT or Diffusion-specific configuration.
3. Pin Python 3.12 and declare the minimum LeRobot ALOHA, Hugging Face,
   MuJoCo/rendering, Gradio, Rerun, FastAPI, and test dependencies.
4. Resolve and commit `uv.lock`; confirm the resolved LeRobot version remains
   compatible with the approved 0.6.1 target. If resolution forces a different
   version, update the architecture brief before proceeding.
5. Write the launcher contract test first. It verifies `help`, non-mutating
   `doctor`, missing-build status, log-path reporting, and idempotent `stop`.

### Gate

```bash
tests/test_app_cli.sh
./app doctor
uv run lerobot-info
```

The phase passes when the launcher behaves correctly without downloading a
checkpoint or claiming the policy is ready.

## Phase 2: Prove the checkpoint and simulator

### Files

- `src/act_aloha_cube_transfer/checkpoint.py`
- `src/act_aloha_cube_transfer/environment.py`
- `src/act_aloha_cube_transfer/policy.py`
- `src/act_aloha_cube_transfer/run.py`
- `tests/test_checkpoint.py`
- `tests/test_environment.py`
- `tests/test_policy.py`

### Checkpoint migration, test first

1. Inspect the installed migration module's current CLI/function signature;
   do not copy a command from memory.
2. Download only the required files from
   `lerobot/act_aloha_sim_transfer_cube_human` at
   `ba73b2766f1371cdc133ca4efb97eb090d744625`.
3. Run LeRobot's official normalization migration into a separate immutable
   cache directory. Never modify the Hub snapshot in place.
4. Verify the migrated directory contains policy config, weights,
   preprocessor, postprocessor, and every declared processor state artifact.
5. Write a manifest containing source repository, revision, source file
   hashes, migration implementation/version, migrated file hashes, and policy
   shape contract.
6. Make `./app build` idempotent: reuse only a complete manifest whose hashes
   match; rebuild incomplete or mismatched output explicitly.

### Environment, test first

1. Construct the current LeRobot ALOHA environment for
   `AlohaTransferCube-v0` with synchronous execution and RGB-array rendering.
2. Assert the observation keys, 480-by-640 top-camera frame, fourteen-element
   robot state, and fourteen-element action contract against the policy config.
3. Reset twice with one seed and assert identical initial numeric state and
   frame hash.
4. Step valid actions, render non-flat frames, observe reward stages, and close
   without leaked MuJoCo resources.
5. Repeat reset/render/step on macOS and in the later Linux image; rendering
   backends may differ, state semantics may not.

### Policy, test first

1. Load the migrated processor pipelines and ACT weights on CPU.
2. Run one real processed observation through `select_action`; assert a finite
   100-by-14 action chunk within the environment bounds.
3. Run the same fixed observation on MPS when available. Compare shape,
   finiteness, and bounded numeric tolerance rather than demanding bit parity.
4. Record CPU and MPS load time, warm inference latency, and peak process RSS.
5. Fail clearly on a missing processor, wrong camera key, state/action mismatch,
   or unsupported MPS operator; never silently construct random processors.

### Gate

```bash
./app build
uv run pytest tests/test_checkpoint.py tests/test_environment.py tests/test_policy.py -v
```

Do not begin the UI if migration, environment parity, or one real policy
forward pass fails. Update the architecture brief if the approved stack must
change.

## Phase 3: Build the rollout engine

### Files

- `src/act_aloha_cube_transfer/rollout.py`
- `src/act_aloha_cube_transfer/types.py`
- `tests/test_rollout.py`
- `tests/test_smoke.py`

### Work

1. Define typed rollout events for frame, step, policy-call index, predicted
   chunk, executed action, reward stage, timing, cancellation, and result.
2. Write fast tests with deterministic policy/environment doubles for:
   horizon 25/50/100 scheduling, replanning boundaries, final partial chunks,
   cancellation, exception cleanup, and terminal result classification.
3. Add the real path: preprocess observation, predict 100 actions, execute the
   chosen horizon, stream every simulator step, and replan until termination or
   the episode limit.
4. Derive task phases directly from gym-aloha reward stages and label them as
   simulator stages, not inferred physical guarantees.
5. Keep simulation execution independent from display rate so a hosted rollout
   can animate smoothly without changing policy/environment timing.
6. Add one real-policy smoke test that performs at least two policy calls and
   validates changing frames, finite actions, increasing step indices, and
   cooperative cancellation.

### Gate

```bash
uv run pytest tests/test_rollout.py -v
make smoke
```

`make smoke` must exercise the pinned migrated checkpoint and real simulator;
it may use a bounded episode but cannot replace inference with a fixture.

## Phase 4: Calibrate evidence and reference seeds

### Files

- `src/act_aloha_cube_transfer/calibration.py`
- `outputs/demo/evidence.json`
- `assets/recordings/` for selected small reference media
- `tests/test_evidence.py`

### Work

1. Add a resumable calibration command that writes each seed result at episode
   boundaries and never discards failures.
2. Evaluate a bounded seed set first on CPU and MPS using the reference
   100-action execution horizon.
3. Preserve seed, device, revision, environment/dependency versions, reward
   trace, success, episode steps, and policy latency for every attempt.
4. Select at least one repeatable successful seed only after replaying it.
5. Run a small fixed multi-seed regression and record the observed result
   without implying it reproduces the published 500-episode 83% study.
6. Store the published aggregate, live calibration, and individual rollout
   evidence in separate schema sections.

### Gate

```bash
make calibrate
uv run pytest tests/test_evidence.py -v
```

The phase passes with a replayable successful reference seed, complete failure
records, and an evidence file whose labels cannot conflate published and local
results.

## Phase 5: Add the browser workspace and Rerun

### Files

- `src/act_aloha_cube_transfer/demo/__init__.py`
- `src/act_aloha_cube_transfer/demo/app.py`
- `src/act_aloha_cube_transfer/demo/theme.py`
- `src/act_aloha_cube_transfer/telemetry.py`
- `tests/test_demo.py`

### Work

1. Reuse the Robium dark workspace theme and compact header proportions from
   the PushT and Robot Navigation demos.
2. Build controls for official policy evidence, horizon 25/50/100, seed,
   randomize, replay, run, and stop. Radio controls must retain visible selected
   dots and keyboard behavior.
3. Make a complete inline PNG/JPEG payload the primary live frame so every
   update remains loaded and opaque; do not stream temporary file URLs.
4. Show current simulator phase, step, policy-call count, chunk position,
   reward, success, and inference latency.
5. Log top-camera frames, predicted chunk, executed actions, fourteen joints,
   reward stages, and chunk boundaries to Rerun. The direct frame remains useful
   if Rerun is hidden or fails to load.
6. Include the selected recorded successful rollout and explicit model-card
   evidence, each labeled separately from the live session.
7. Test Gradio API behavior, serialized runs, cancellation, valid inline image
   decoding, changing frames, evidence labels, and full terminal results.

### Gate

```bash
make demo-smoke
./app run
./app status
./app stop
```

Run a browser acceptance check for continuous loaded frames, visible control
state, successful replay, responsive stop, and no inherited top padding.

## Phase 6: Add the hosted gateway and CPU image

### Files

- `src/act_aloha_cube_transfer/demo/gateway.py`
- `docker/demo.Dockerfile`
- `scripts/demo_container_smoke.py`
- gateway tests in `tests/test_demo.py`

### Work

1. Adapt the existing capability-protected claim, health, start/status/stop,
   expiration, and `/ui` mount contract.
2. Load the real policy on a background thread and report ready only after the
   environment and warm inference probe pass.
3. Bake the migrated model and manifest into a multi-stage CPU image; set Hub
   offline flags in the runtime stage.
4. Select the Linux MuJoCo headless backend and verify actual rendered frames.
5. Run the same reference seed and cancellation checks through the container
   gateway API.
6. Measure warm CPU policy-call pauses and full visible episode duration.

### Gate

```bash
make demo-image
make demo-container-smoke
```

Hosted integration is allowed only when every replan pause is near or below
two seconds and the reference episode completes in under one minute. If the
gate fails, keep the native app complete and update the architecture decision
before considering a GPU service.

## Phase 7: Finish the reference application

### Files

- `README.md`
- `robium-app.yaml`
- `docs/architecture-brief.md`
- `docs/case-study.md` after real evidence exists
- repository-root `REGISTRY.md`
- final GIFs and stills under `assets/`

### Work

1. Document `./app` as the public interface and keep research/internal Make
   targets secondary.
2. Explain ACT, action chunks, execution horizon, ALOHA, published evidence,
   local evidence, device behavior, and model migration in Robium's team voice.
3. Update the architecture brief from draft to active and replace resolved
   risks with measured outcomes; leave genuinely open risks visible.
4. Add the app registry row and detailed card in the same app-completion commit.
5. Capture a clean successful rollout, workspace view, chunk timeline, and
   evidence still only from passing real runs.
6. Run a clean-checkout/native smoke and a production-shaped container smoke.

### Gate

```bash
./app doctor
make smoke
make demo-smoke
make demo-container-smoke
git diff --check
```

The app is not complete until these pass and `REGISTRY.md` records the same
verified date and pass bar.

## Phase 8: Integrate the website locally

This phase begins only after phase 7 is green and uses the website repository's
own AGENTS.md and live-demo rules.

### Work

1. Add a dedicated demo detail page with live and local options.
2. Add the per-demo frontend workspace and orchestrator JSON without changing
   unrelated demo files.
3. Ingest the app-owned case study and media through the existing article
   pipeline.
4. Add exact smoke assertions for the demo route, article, hero/social media,
   and lifecycle island.
5. Run the full local site + orchestrator + container lifecycle: idle, start,
   booting, ready, real rollout, replay, stop, container removed.

### Gate

```bash
cd /Users/mdemirst/repos/robium-website
make smoke
```

Production image publication and Cloud Run/site deployment remain separate
mutations and require explicit authorization after local verification.

## Completion record

- Native app smoke, real-policy smoke, browser acceptance, and the
  production-shaped CPU container smoke passed on 2026-08-23.
- The official checkpoint produced a repeatable successful transfer for seed
  1001; the verified CPU container run completed at step 227.
- The website choice page, tutorial, real workspace still, orchestrator
  registry, private Start/READY/Stop lifecycle, and container cleanup all
  passed locally.
- No production image publication, Cloud Run mutation, site deployment, or
  push was performed.

## Commit sequence

Keep commits independently reviewable and exclude the existing unrelated dirty
files in the shared worktrees:

1. `feat(act-aloha): scaffold launcher and environment`
2. `feat(act-aloha): migrate and load official checkpoint`
3. `feat(act-aloha): add chunked rollout and calibration`
4. `feat(act-aloha): add live workspace and telemetry`
5. `feat(act-aloha): add hosted CPU gateway`
6. `docs(act-aloha): publish reference app evidence`
7. Website integration in the website repository after the app gate passes.

Each commit stages only its named ACT ALOHA files and required registry entry.
No existing PushT, Robot Navigation, VLA, brand, or unrelated asset changes are
included.
