# Architecture Brief: ACT ALOHA Cube Transfer

**Date:** 2026-08-23
**Status:** active — locally verified
**Author:** main agent refinement, approved in conversation

## 1. Requirements

Build a second physical-AI reference application that demonstrates Action
Chunking with Transformers on a task for which ACT is a natural fit. The app
must use the official pretrained LeRobot ALOHA Transfer Cube checkpoint rather
than require a new training run.

The MVP requirements are:

- Run `gym_aloha/AlohaTransferCube-v0`, a simulated bimanual transfer task.
- Pin and use `lerobot/act_aloha_sim_transfer_cube_human`, whose model card
  reports 83% success over 500 episodes for the 80k checkpoint.
- Run natively on Apple Silicon using MPS when supported, with CPU fallback.
- Provide the same public operator contract as the other reference apps:
  `./app doctor|build|run|status|logs|stop`.
- Provide a browser workspace with a direct live simulation view, seeded
  replay, randomized layouts, execution-horizon controls, published evidence,
  and an additive Rerun timeline.
- Produce a CPU container suitable for a private per-visitor hosted session,
  but publish the hosted path only after measured latency passes the bar in
  section 8.
- Keep the official 83% aggregate result separate from every individual live
  or recorded rollout.
- Do not add ALOHA Insertion, policy training, real hardware, or alternate
  checkpoints to v1.

Host preflight on 2026-08-23 reported macOS arm64, Apple MPS, Docker 29.6.1,
409 GB free disk, Python 3.14.6, and uv 0.11.29. The project will still pin
Python 3.12 because LeRobot supports it and the sibling learning applications
already exercise that interpreter.

## 2. Chosen stack + reasoning

| Layer | Choice | Version or revision | Why, and what was rejected |
| --- | --- | --- | --- |
| Middleware | None | N/A | This is one learned policy in one simulation process. ROS 2 would add packaging and transport without serving the MVP. |
| Simulator | `gym-aloha` on MuJoCo | Exact compatible releases pinned in `uv.lock` after the feasibility test | ALOHA Transfer Cube is the canonical ACT demonstration and is available without an NVIDIA GPU. Isaac Sim was rejected because it is unnecessary, GPU-gated, and unsupported on macOS. |
| Learning runtime | LeRobot | 0.6.1 target, PyPI-verified 2026-08-23 | LeRobot owns the official checkpoint, ACT implementation, ALOHA environment configuration, and evaluation contract. A custom ACT runtime was rejected. |
| Policy | Official LeRobot ACT Transfer Cube | Model revision `ba73b2766f1371cdc133ca4efb97eb090d744625` | The model card reports 83% success over 500 episodes and the weights are approximately 207 MB. Retraining was rejected because it costs GPU time and may not reproduce the published result. Community checkpoints were rejected because their evidence is weaker. |
| Policy compatibility | LeRobot normalization migration | Tool shipped with the pinned LeRobot source | The official checkpoint predates processor-pipeline files. Use the upstream migration path and verify its artifacts; do not synthesize normalization from a different dataset or silently fall back. |
| Local environment | uv, Python 3.12, native MPS/CPU | Exact dependency set in `uv.lock` | This is a pure-Python learning stack. Native uv preserves MPS on macOS; Docker Desktop cannot expose MPS. |
| Hosted environment | Multi-stage Linux CPU image with uv-managed environment | Base image and lockfile pinned during implementation | A baked model and migrated processor bundle give reproducible, offline startup. GPU hosting is unnecessary unless the CPU latency gate fails. |
| Application UI | Gradio direct-frame workspace | Pin after compatibility test | It matches the PushT reference-app interaction model and supports local and hosted use. A standalone native MuJoCo viewer was rejected because it is not remotely viewable. |
| Telemetry | Rerun, additive to the direct frame | Pin compatible SDK versions in `uv.lock` | Rerun can show action chunks, executed actions, reward stages, and joint trajectories. It must not be the only way to see a rollout. |
| Hosted lifecycle | Existing Robium FastAPI session gateway and website orchestrator contract | Reuse the proven per-visitor interface | Reusing the established start/status/stop contract is safer than inventing a second demo lifecycle. |

The primary donor is `diffusion-policy-pusht`: reuse its repository layout,
launcher contract, direct inline-frame streaming, evidence labeling, gateway
shape, and layered smoke tests. Replace its policy, simulator, controls, and
metrics rather than copying Diffusion-specific adapter logic.

## 3. Module breakdown

| Module | Responsibility | Inputs | Outputs |
| --- | --- | --- | --- |
| `checkpoint` | Download the pinned Hub revision, invoke the official processor migration, validate required files and hashes, and write a compatibility manifest. | Hub model revision, LeRobot migration tool | Immutable local migrated model directory and manifest |
| `environment` | Construct `AlohaTransferCube-v0`, apply an exact seed, expose RGB frames and reward stages, and close cleanly. | Seed, render/headless configuration | Observations, frames, rewards, termination state |
| `policy` | Load ACT on MPS or CPU, validate the 14-dimensional state/action contract and top-camera input, and predict 100-action chunks. | Migrated checkpoint, observation batch | Action chunk and inference timing |
| `rollout` | Run receding-horizon episodes, execute 25/50/100 actions per prediction, support cancellation, and compute per-episode status. | Policy, environment, execution horizon, seed | Streamed frames, chunk events, final result |
| `telemetry` | Log frames, predicted and executed actions, fourteen joint dimensions, reward stages, and chunk boundaries. | Rollout events | Rerun recording/stream and compact result summary |
| `demo` | Render controls, evidence, direct inline frame, health, recorded reference rollout, and embedded Rerun view. | User controls and rollout stream | Browser workspace |
| `gateway` | Claim one visitor session, load the real policy in the background, expose lifecycle state, mount the UI, serialize rollouts, and shut down cooperatively. | Orchestrator capability and browser requests | Start/status/stop API and `/ui` |
| `./app` | Present the common six-command operator interface and delegate to native setup/runtime scripts. | Operator command | Diagnostics, build, process lifecycle, logs |
| `tests` | Verify migration contracts, deterministic resets, real inference, rollout behavior, device parity, container startup, and browser lifecycle. | App artifacts and runtime | Pass/fail evidence and calibration reports |

## 4. Comms plan

The native app is one Python process. Environment, policy, rollout, telemetry,
and UI communicate through typed in-process values and callbacks; there is no
ROS 2 or internal network transport.

The rollout event contract contains:

- monotonic step and policy-call indices;
- seed and execution horizon;
- current RGB frame;
- predicted 100-by-14 action chunk;
- executed action index and fourteen-dimensional command;
- environment reward and derived task phase;
- inference latency, cancellation state, and terminal result.

The browser talks to Gradio over its normal HTTP/WebSocket path. The direct
frame uses a stable inline image payload so component URL replacement cannot
introduce fades or black gaps. Rerun receives the same rollout events and is an
optional inspection surface.

For hosted use, the existing website orchestrator talks to the app gateway via
the proven start/status/stop lifecycle. The gateway reports ready only after
the checkpoint, processors, environment, and one real inference pass succeed.
One claimed container serves one visitor, and only one rollout runs at a time.

## 5. Environment strategy

### Native macOS

- Pin Python 3.12 with `.python-version`.
- Declare all Python dependencies in `pyproject.toml` and commit `uv.lock`.
- Run commands through `uv run`; never install into system Python.
- Use MPS when the ACT operator set passes the device smoke test; otherwise
  display the explicit CPU fallback in health/status output.
- Keep MuJoCo offscreen rendering independent of the browser UI.

### Hosted and Linux CPU

- Build a multi-stage image from a pinned Python base.
- Resolve the same `uv.lock` inside the image.
- Migrate and validate the pinned checkpoint in the builder stage, then copy
  only the environment, model artifacts, application, and required runtime
  libraries into the final image.
- Run with Hub offline flags so visitor startup never depends on a live model
  download.
- Select and test the appropriate MuJoCo headless backend for the target Linux
  image; do not assume the macOS backend applies.

Local and hosted runs share checkpoint revision, migration implementation,
policy configuration, seed semantics, rollout logic, and tests. Their only
intended difference is the device (`mps` versus `cpu`) and rendering backend.

## 6. Data plan

No training data is required for ordinary operation. The application is
offline-first and uses existing official artifacts:

- Model: `lerobot/act_aloha_sim_transfer_cube_human`, pinned to
  `ba73b2766f1371cdc133ca4efb97eb090d744625`.
- Published evidence: model-card 83% success over 500 episodes and its attached
  `eval_info.json`; preserve the model card's caveat that success registration
  may differ from the original ACT implementation.
- Training provenance: `lerobot/aloha_sim_transfer_cube_human`, currently
  described as 50 demonstrations, 20,000 frames, one 480-by-640 top camera,
  and fourteen-dimensional state/actions.

The normal build downloads only model artifacts. Dataset metadata may be
cached for provenance checks, but the full dataset is not needed unless a
future training mode is explicitly designed.

Downloaded source artifacts, migrated checkpoints, recordings, rollout videos,
Rerun files, and evaluation outputs are gitignored. Small evidence manifests,
calibration summaries, and selected reference media may be committed with
their source revision recorded.

## 7. Robium skills per build phase

| Phase | Skill(s) |
| --- | --- |
| Requirements and architecture | `brainstorming` then `architect` |
| Environment and checkpoint compatibility | `environments`, `lerobot`, `huggingface` |
| Data provenance | `data`, `huggingface` |
| Simulation integration | `lerobot`; use `mujoco` only if gym-aloha integration requires lower-level rendering work |
| Rollout telemetry | `visualization` then `rerun` |
| Module and container integration | `integration` |
| Fixtures and acceptance tests | `testing`, `test-assets` |
| Public interactive demo | `live-demo`, then `cloud-run` after smoke passes |

## 8. Risk results

1. **Legacy checkpoint migration fidelity — resolved locally.** The official
   model has no standalone processor files. The app ran LeRobot's migration,
   verified all remaining model weights, hashed both bundles, and completed
   real rollouts against the pinned revision.

2. **gym-aloha on macOS arm64 — resolved.** The pinned LeRobot 0.6.1 stack
   resets, renders, steps, and completes transfers on Python 3.12. Spawned
   simulator workers keep GLFW on a process main thread.

3. **MPS compatibility and speed — resolved for the app path.** Real 100-by-14
   predictions and complete episodes ran on MPS. The default browser seed
   completed at step 236.

4. **Linux CPU responsiveness — resolved for the reference image.** The
   production-shaped CPU container reported ready only after a real inference,
   completed seed 1001 through the Gradio API, and measured its final policy
   call at 900 ms on Docker Desktop. A GPU host is unnecessary for this app.

5. **Success semantics — explicitly represented.** The UI names gym-aloha's
   five reward stages and reports transfer complete only when the environment
   reaches its terminal reward. It does not claim extended stable handoff.

6. **Repeatable successful seeds — calibrated.** A bounded MPS run preserved
   seeds 1000 through 1004. Seeds 1001 and 1002 succeeded; seed 1001 then
   succeeded again and became the default live example.

7. **Upstream insertion evidence inconsistency — isolated.** ALOHA Insertion
   remains outside v1 and is not presented as comparative evidence.

8. **Live-frame and Rerun embedding regressions — resolved locally.** The app
   uses complete inline JPEG payloads, pins the verified Gradio/Rerun trio,
   and passed an actual browser rollout with the direct frame and populated
   telemetry panels visible.
