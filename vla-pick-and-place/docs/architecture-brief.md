# Architecture Brief: VLA Pick-and-Place

**Date:** 2026-08-23
**Status:** active
**Author:** main-agent refinement from Robium issue #69

The approved design is recorded in
`docs/superpowers/specs/2026-08-23-pi05-libero-runpod-redesign.md`. This brief
is the living architecture contract for implementation.

## 1. Requirements

- **Robot:** simulated Franka Panda supplied by LIBERO/robosuite.
- **Task:** zero-based LIBERO-Goal task 8,
  `put_the_bowl_on_the_plate`, with canonical language instruction
  `put the bowl on the plate`.
- **Policy:** official `lerobot/pi05_libero_finetuned_v044` Pi0.5 checkpoint;
  no custom fine-tune or training wrapper.
- **Simulation:** real LIBERO MuJoCo simulation, fixed official initial states,
  hard resets, simulator-derived success, genuine frames.
- **Evaluation:** 20 sequential episodes, batch size 1, fixed state IDs 0-19
  mapped to seeds 1000-1019, target at least 16/20, no selective reruns or
  easier-task substitution.
- **Local development:** macOS Apple Silicon is a thin development client for
  fixtures, fake policy, replay, UI, evidence validation, and tests. It does not
  run Pi0.5 inference.
- **Real compute:** Linux/amd64, NVIDIA CUDA, one Secure Cloud A100 SXM 80 GB in
  an S3-enabled, currently volume-capable network-volume datacenter. This
  replaces the original A40/A6000 model-name restriction by explicit user
  amendment on 2026-08-23; the single-Pod limit and all other paid gates remain
  unchanged.
- **Hosting:** one isolated RunPod Pod per visitor, maximum one active Pod,
  preloaded network volume, private immutable image, existing website
  orchestrator, capability-scoped direct browser handoff.
- **Production:** deploy with `VLA_LIVE_ENABLED=false`; live production remains
  blocked pending separate explicit approval.
- **Privacy:** do not log edited prompts, observations, or visitor videos.
  Operational logging is limited to phase, GPU, coarse timings, public state
  identifier, prompt class, simulator outcome, deletion reason, and cost.
- **Cost:** $5 maximum tagged VLA RunPod spend per UTC day, including billed
  usage and conservative active reservations; fail closed if spend is not
  verifiable.

Confirmed development host: macOS arm64 with Apple MPS but no CUDA, Docker
29.6.1 available, 370 GB free. This makes the thin-client/GPU-cloud exception
intentional rather than an unresolved local-parity defect.

## 2. Chosen stack + reasoning

| Layer | Choice | Version/revision | Why, and what was rejected |
| --- | --- | --- | --- |
| Middleware | None | n/a | The policy and simulator share one Python process and failure domain. ROS 2 or a second RPC service would add serialization without useful isolation. |
| Policy | LeRobot Pi0.5 | LeRobot `8fff0fde7c79f23a93d845d1a50e985de01f8b8a`; checkpoint `8e174154ef5f6c60a8da12ae99c303d8963138c1` | Official checkpoint already trained and evaluated for LIBERO. SmolVLA/SO-101 is removed. A Robium training wrapper, quantization, and model surgery are rejected. |
| Robot/task | LIBERO Franka Panda, `libero_goal` task 8 | LIBERO `8f1084e3132a39270c3a13ebe37270a43ece2a01` | The issue fixes the embodiment and hero task. Arbitrary scene editing and a multi-task selector are rejected. |
| Simulator | LIBERO on MuJoCo EGL | pinned through the locked LeRobot/LIBERO environment | It provides the official task, fixed initial states, cameras, action contract, and sparse success signal. The old custom SO-101 scene and local CGL inference path are removed. |
| UI | Gradio behind a FastAPI gateway | lockfile-pinned | It can stream real frames and progress while the gateway owns capability isolation, lifecycle status, and shutdown. Pause, step, and manual control are excluded. |
| Local test policy | Deterministic fake policy plus recorded RGB fixtures | application-owned | Free, deterministic coverage of orchestration, streaming, UI, evidence, and lifecycle before paid compute. It is visibly marked fake and never used for measured claims. |
| Runtime environment | Multi-stage Linux/amd64 CUDA Docker image with uv-managed venv | CUDA 12.4.1 cuDNN Ubuntu 22.04 images pinned by digest; Python 3.10 | Native dependencies, EGL, CUDA, and RunPod require Docker. A local MPS/CPU Pi0.5 path is explicitly rejected. |
| Checkpoint storage | Private RunPod network volume mounted read-only by convention at `/models` | immutable checkpoint revision above | Avoids visitor-time Hub download and keeps weights out of the private image. Baking weights or exposing a browser token is rejected. |
| Evidence storage | Public Hugging Face dataset plus compact Git summary | immutable dataset revision recorded after publication | The Hub holds 20 videos and per-episode data; Git holds schema, manifest, summary, previews, and immutable revision, avoiding duplicate evidence. |
| Live compute | RunPod Secure Cloud Pod | exact A100 SXM 80 GB allowlist | Required NVIDIA CUDA capacity with per-visitor isolation and verified S3 volume locality. Smaller silent fallbacks and Cloud Run CPU inference are rejected. |
| Control plane | Existing TypeScript/Fastify demo orchestrator with provider router | repository lockfile | Preserves existing Cloud Run and local Docker behavior and avoids a second lifecycle service. |
| Budget state | RunPod billing/Pod APIs plus atomic GCS ledger | one UTC-day object per date | RunPod billing omits names/template IDs after deletion, so a durable owned-Pod mapping is required. A waiting queue or queue database is not introduced. |

The CUDA builder and runtime manifest digests are respectively
`sha256:622e78a1d02c0f90ed900e3985d6c975d8e2dc9ee5e61643aed587dcf9129f42`
and `sha256:2fcc4280646484290cc50dce5e65f388dd04352b07cbe89a635703bd1f9aedb6`.

## 3. Module breakdown

### Application repository

| Module | Responsibility | Inputs | Outputs |
| --- | --- | --- | --- |
| `config` | Immutable revisions, task/state mapping, prompt and runtime limits | environment overrides limited to paths/mode/port/capability | validated typed configuration |
| `libero_task` | Resolve task 8, fixed states, hard resets, observations, actions, success | pinned LIBERO install; state ID | observation stream and simulator result |
| `policy` | Shared policy protocol, real Pi0.5 adapter, deterministic fake policy | observation and prompt | seven-dimensional actions and latency samples |
| `rollout` | Single-episode lock, cancellation, frame/progress streaming, hard reset | task, policy, prompt, state | complete/cancelled result and metrics |
| `evidence` | Per-episode records, aggregation, schema validation, SHA-256, publication config | completed real episodes | manifest, summaries, videos, hashes |
| `ui` | Prompt/state controls, provenance labels, streamed frames, result | gateway-owned runner | Gradio application |
| `gateway` | Capability-scoped claim/status/shutdown/UI/stream and process lifecycle | capability and expiry | protected HTTP interface |
| `cli` | Test, serve, evaluate, manifest, and reproduce entry points | validated config | deterministic commands and exit codes |

The `vla_pick_and_place` Python package identity remains stable. Old SO-101,
SmolVLA, oracle, custom-dataset, spike, training, and Rerun modules are removed
from the active tree.

### Website repository

| Module | Responsibility |
| --- | --- |
| demo JSON | Select `runpod`, image, GPU allowlist, volume, port, timeouts, concurrency, and budget. |
| provider router | Choose local Docker in local mode, Cloud Run for existing production demos, and RunPod for the VLA. |
| RunPod API client/driver | Create, inspect, list, delete, and reconcile only owned Pods. |
| budget ledger | Atomically combine current-day billed owned Pod IDs with active reservations and fail closed. |
| manager/API | Expose complete human-readable lifecycle phases and disabled/busy/budget errors. |
| VLA workspace | Start/stop/retry, direct capability-scoped iframe handoff, responsive status, recorded-evidence fallback. |
| article | Explain VLAs, distinguish upstream 97.5% from Robium's manifest result, and display three state outcomes. |

## 4. Comms plan

Inside the Pod, simulator, policy, rollout coordinator, evidence hooks, and UI
communicate by direct Python calls and in-process queues. Frames remain in memory
and are encoded only for the Gradio stream/video writer.

The orchestrator uses RunPod's authenticated REST API to provision and delete
Pods and query billing. It polls the capability-scoped gateway only for coarse
readiness/status. After allocation it returns the direct RunPod proxy host plus
capability path to the browser. The browser then talks directly to the Pod for
claim, status, UI assets, API calls, and streaming. The orchestrator is not in
the frame/action path.

All Pod gateway routes live under `/c/{capability}/...`. Missing or foreign
capabilities and unrelated paths return 404. RunPod and Hugging Face credentials
never cross into browser payloads. The live Pod does not need a Hugging Face
token because the accepted snapshot is already on the attached volume.

## 5. Environment strategy

This application uses Docker because CUDA, EGL, native simulation dependencies,
and the exact Linux host environment are part of correctness. uv manages one
project venv inside the image; no dependency is installed into system Python.

- **Builder:** pinned CUDA 12.4.1 cuDNN-devel Ubuntu 22.04 digest.
- **Runtime:** pinned CUDA 12.4.1 cuDNN-runtime Ubuntu 22.04 digest.
- **Python:** 3.10, satisfying pinned LeRobot v0.4.4.
- **Dependency source:** committed `pyproject.toml` and `uv.lock`, with LeRobot
  and LIBERO exact Git commits.
- **Rendering:** `MUJOCO_GL=egl` on Linux; no X11/Wayland dependency.
- **GPU:** RunPod host supplies NVIDIA driver/container runtime; the app verifies
  CUDA availability and permitted GPU type before real mode.
- **Checkpoint:** `/models/lerobot/pi05_libero_finetuned_v044/8e174154ef5f6c60a8da12ae99c303d8963138c1` in
  offline mode; startup validates revision and required files.
- **Local:** the same package and gateway run in fake mode with fixtures. Real
  inference commands fail clearly on macOS or without CUDA.

The CPU/fake gateway target proves the committed container definition and HTTP
lifecycle without claiming GPU parity. The paid feasibility smoke is the real
environment-parity acceptance test.

## 6. Data plan

### Inputs

- official Pi0.5 snapshot at the immutable Hugging Face revision;
- official LIBERO task assets and fixed initial states at the pinned revision;
- three curated UI state IDs 0, 1, and 2;
- publication evaluation state IDs 0 through 19; and
- small application-owned fake RGB fixtures containing no visitor data.

### Outputs

Each real episode produces a video and JSON record with simulator outcome,
timings, state, seed, configuration, revisions, and hash. The aggregate manifest
derives counts from episode records and rejects zero or non-20 publication runs.

The public Hugging Face dataset stores all full evidence. Git stores only the
schema, validated manifest, result summary, three compact previews, and immutable
dataset revision. No checkpoint, full video set, edited prompt, visitor
observation, or visitor video is committed or retained.

The article and README read measured claims from the validated manifest. They do
not duplicate hand-entered success numbers.

## 7. Robium skills per build phase

| Phase | Skill(s) |
| --- | --- |
| Approved design and active brief | brainstorming, architect |
| Environment decision | environments |
| Module/process and Docker boundaries | integration |
| Pi0.5 and LIBERO application | lerobot |
| Local and GPU test assets | test-assets |
| Unit, integration, container, and real smoke gates | testing |
| Evidence publication | huggingface, data |
| Public RunPod demo | live-demo |
| App-scoped findings and end-of-block retros | learning capture only; no skill edits |

## 8. Open risks

| Risk | What it blocks | Resolution/gate |
| --- | --- | --- |
| Exact-runtime memory use is unmeasured | Feasibility and all later paid work | Measure the one A100 SXM 80 GB run; do not create a second fallback Pod or optimize the model. |
| Exact policy/environment seam may expose pinned-v0.4.4 defects | Real rollout | First paid smoke must load processor files and reach simulator-derived completion before evaluation. |
| Required RunPod credentials, credit, private registry, template, accepted Gemma licensing, and network volume may be absent | First paid gate | Preflight without creating resources; stop and report if any requirement is unavailable. |
| A100 SXM Secure Cloud capacity may be unavailable | Feasibility/live flow | Fail visibly; do not choose a smaller or different GPU. Retry the allocation later without creating duplicate Pods. |
| RunPod proxy behavior may differ from local gateway behavior | Live handoff | Measure proxy and direct capability routes during feasibility; do not proceed to evaluation/live integration if genuine streaming is unreliable. |
| RunPod billing data can lag or omit ownership metadata | $5 enforcement | Durable owned-Pod ledger plus billing and active reservation reconciliation; fail closed on missing/stale/unverifiable inputs. |
| Capability prefix may be bypassed by Gradio asset/API routes | Public isolation | Route-level tests for root, assets, API, and stream with correct/missing/foreign capabilities; real smoke before deployment. |
| Pod deletion can be delayed or fail | Cost and privacy | Delete on every terminal path, poll until absent, reconcile owned expired Pods on restart, and fail closed while an owned Pod remains. |
| Measured 20-episode score may be below 16/20 | Headline target | Publish the valid lower score unchanged with a prominent warning and expected-failure disclosure. |
| Production could be enabled accidentally | Unauthorized paid sessions | Default and deployed `VLA_LIVE_ENABLED=false`; tests assert disabled allocation; separate explicit approval is required to change it. |
