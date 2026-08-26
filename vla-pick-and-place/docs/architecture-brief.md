# Architecture Brief: VLA Pick-and-Place

**Date:** 2026-08-23   **Last amended:** 2026-08-24
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
- **Real compute:** Linux/amd64, NVIDIA CUDA, one Secure Cloud RTX PRO 4500
  Blackwell Server Edition 32 GB in `US-KS-2`, subject to a fresh live capacity
  preflight. This inference-only choice was explicitly approved on 2026-08-24
  after exact checkpoint sizing showed 7,473,096,344 weight bytes at batch size
  1 and larger A100/H100 paths repeatedly failed before compute. The one-Pod
  limit and all other paid gates remain unchanged.
- **Hosting:** one isolated RunPod Pod per visitor, maximum one active Pod,
  validated persistent network volume, private immutable image, existing website
  orchestrator, capability-scoped direct browser handoff.
- **Production:** the reusable RunPod template defaults to
  `VLA_LIVE_ENABLED=false`; after explicit operator approval on 2026-08-26, the
  production controller overrides it to `true` behind the one-Pod and $5/day
  gates. Rollback restores the controller and site to their disabled revisions.
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
| Checkpoint storage | Existing private RunPod network volume `68s0bxbv7p` in `US-KS-2`, mounted read-only by convention at `/models` after bootstrap; transient container-disk staging before load | checkpoint `8e174154ef5f6c60a8da12ae99c303d8963138c1`; PaliGemma tokenizer `35e4f46485b4d07967e7e9935bc3786aad50687c` | The bootstrap verifies the model hash plus the separately gated tokenizer snapshot, writes revision markers last, removes the Hub token from child processes, and switches to offline mode. Startup copies the verified 7.47 GB snapshot sequentially to container disk before LeRobot memory-maps it; random tensor reads directly from the RunPod network volume stalled after state-dict discovery. Baking weights or exposing a browser token is rejected. |
| Evidence storage | Public Hugging Face dataset plus compact Git summary | immutable dataset revision recorded after publication | The Hub holds 20 videos and per-episode data; Git holds schema, manifest, summary, previews, and immutable revision, avoiding duplicate evidence. |
| Feasibility compute | RunPod Secure Cloud Pod | exact `NVIDIA RTX PRO 4500 Blackwell Server Edition`, 32 GB | It is the current US candidate colocated with the proven `US-KS-2` volume. The pinned model is 7.47 GB of BF16/F32 weights at batch size 1, while the locked PyTorch 2.10 CUDA 12.8 environment supports Blackwell. The Pod must prove host-driver/device compatibility and measured peak VRAM; no fallback or model/config optimization is allowed. |
| Production live compute | RunPod Secure Cloud Pod | enabled; exact allowlist of RTX PRO 4500 Blackwell Server Edition 32 GB, A40 48 GB, or RTX A6000 48 GB | On 2026-08-26 the operator explicitly approved production enablement. The public lifecycle smoke passed on the available 32 GB RTX PRO 4500 Server Edition; the immutable image, one-Pod limit, capability, budget, and lifetime contracts remain unchanged. The reusable template stays default-off and the production controller owns the explicit live override. |
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
| `startup` | Verify the persistent snapshot and tokenizer, stage them to transient container disk, and switch child processes offline | private network volume; optional bootstrap token | local staged checkpoint path and sanitized phase evidence |
| `rollout` | Single-episode lock, cancellation, frame/progress streaming, hard reset | task, policy, prompt, state | complete/cancelled result and metrics |
| `evidence` | Per-episode records, aggregation, schema validation, SHA-256, publication config | completed real episodes | manifest, summaries, videos, hashes |
| `diagnostics` | Atomically persist the current startup stage and a sanitized bounded failure summary | startup stage, exception, process environment used only for redaction | `phase.json`, `failure.json` on the attached volume |
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

The orchestrator uses RunPod's authenticated GraphQL API for Pod creation
because the current REST create endpoint rejects the exact Server Edition GPU
inventory ID and cannot express this proven template/volume contract. It uses
the REST API for Pod reads, deletion, and billing. It polls the
capability-scoped gateway only for coarse readiness/status. After allocation it
returns the direct RunPod proxy host plus capability path to the browser. The
browser then talks directly to the Pod for claim, status, UI assets, API calls,
and streaming. The orchestrator is not in the frame/action path.

Before the gateway is reachable, startup progress is observed from durable
volume markers: `phase.json`, `failure.json`, `cuda-preflight.json`, the
checkpoint `REVISION`, and finally `feasibility.json`. The current phase is
atomically replaced at CUDA preflight, checkpoint validation/bootstrap,
model loading, rollout, artifact writing, and gateway handoff. Failure evidence
contains no traceback or environment dump and redacts credential values and
token shapes. RunPod's Pod `runtime` and port fields remain supporting signals,
not the sole source of truth, because the corrected feasibility attempt wrote
valid volume evidence while those fields stayed empty.

The immutable GPU entrypoint has three explicit modes: gateway-only,
one-episode feasibility, and the fixed 20-episode publication evaluation.
Evaluation mode receives the immutable application commit, image digest, GPU
name, and persistent output path as validated environment inputs; stages the
verified checkpoint to transient disk; runs the compiled evaluator offline;
writes every candidate artifact plus a durable completion phase to the network
volume; releases model memory when the evaluator exits; and keeps only the
lightweight startup process alive until the controller verifies evidence and
deletes the Pod. Hugging Face publication and final cost/revision resolution
happen off-Pod after deletion.

All Pod gateway routes live under `/c/{capability}/...`. Missing or foreign
capabilities and unrelated paths return 404. RunPod and Hugging Face credentials
never cross into browser payloads. The live Pod does not need a Hugging Face
token after the accepted checkpoint and tokenizer snapshots are on the attached
volume.

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
- **LIBERO configuration:** the immutable image bakes
  `/app/libero-config/config.yaml`, sets
  `LIBERO_CONFIG_PATH=/app/libero-config`, and resolves assets, BDDL files,
  initial states, and the benchmark root from the exact `/opt/libero` checkout.
  Headless startup never creates a home-directory config or reads stdin.
- **GPU:** RunPod host supplies NVIDIA driver/container runtime; the baked image
  verifies the exact device, driver, CUDA runtime, supported compute
  architecture, and a minimal CUDA tensor operation before any checkpoint
  download.
- **Checkpoint:** `/models/pi05-libero-v044`. On the one newly authorized,
  successfully allocated RTX PRO 4500 Blackwell Server Edition feasibility Pod
  in `US-KS-2`, a feasibility-only bootstrap downloads revision
  `8e174154ef5f6c60a8da12ae99c303d8963138c1`, verifies required files and
  model SHA-256
  `877b3ec1130548b69af7f8aeef3ec9d3fc7738040f0b9beb490857ec970997ae`,
  writes `REVISION` atomically as the final step, removes `HF_TOKEN` from the
  feasibility and gateway child environments, and forces Hub/Transformers
  offline. The measured feasibility command runs once and then execs the
  capability gateway on the same Pod for proxy/cancellation checks. All later
  starts only validate and load this path offline.
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
schema, validated manifest, result summary, three compact previews, and a
`publication.json` pointer containing the immutable dataset revision plus the
manifest hash. The revision is resolved only after the complete dataset commit;
it is not embedded into that same manifest because a Git commit cannot contain
its own content-dependent hash. No checkpoint, full video set, edited prompt,
visitor observation, or visitor video is committed or retained.

The article and README read measured claims from the validated manifest. They do
not duplicate hand-entered success numbers.

The real adapter has two explicit execution profiles. Feasibility and the
20-episode publication evaluation use the checkpoint's default compiled path.
The interactive gateway uses eager execution, based on the measured feasibility
result where compilation dominated the first action while subsequent eager
actions completed quickly. The UI reports starting immediately, disables the
run control during an active episode, and renders duplicate requests as a busy
state rather than an exception.

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
| Exact-runtime memory use is unmeasured | Feasibility and all later paid work | Measure the one RTX PRO 4500 Blackwell Server Edition 32 GB run; do not create a second fallback Pod or optimize the model/configuration. |
| Exact policy/environment seam may expose pinned-v0.4.4 defects | Real rollout | First paid smoke must load processor files and reach simulator-derived completion before evaluation. |
| Dependency-installed `hf-libero` can shadow the pinned checkout and omit runtime assets | Model loading | Make `/opt/libero` the authoritative Python import source and assert in the built GPU image that LIBERO's module path and required scene XML both resolve under that exact checkout. |
| Same-Pod checkpoint bootstrap may fail | Feasibility only | Never write the revision marker before full hash/file validation; delete the one Pod in `finally`, preserve the volume for diagnosis, and block all later paid work. |
| Required RunPod credentials, credit, private registry, template, accepted Gemma licensing, and network volume may be absent | First paid gate | Preflight without creating resources; stop and report if any requirement is unavailable. |
| RTX PRO 4500 Server Edition capacity or Blackwell host compatibility may fail | Feasibility | Preflight exact `NVIDIA RTX PRO 4500 Blackwell Server Edition` stock in `US-KS-2`. After allocation, verify the exact device, host driver, PyTorch CUDA 12.8 runtime, supported compute capability, and a CUDA tensor operation before downloading weights. Fail visibly, delete in `finally`, and do not choose a different GPU or create a duplicate Pod. |
| RunPod proxy behavior may differ from local gateway behavior | Live handoff | Measure proxy and direct capability routes during feasibility; do not proceed to evaluation/live integration if genuine streaming is unreliable. |
| RunPod billing data can lag or omit ownership metadata | $5 enforcement | Durable owned-Pod ledger plus billing and active reservation reconciliation; fail closed on missing/stale/unverifiable inputs. |
| Capability prefix may be bypassed by Gradio asset/API routes | Public isolation | Route-level tests for root, assets, API, and stream with correct/missing/foreign capabilities; real smoke before deployment. |
| Pod deletion can be delayed or fail | Cost and privacy | Delete on every terminal path, poll until absent, reconcile owned expired Pods on restart, and fail closed while an owned Pod remains. |
| Measured 20-episode score may be below 16/20 | Headline target | Publish the valid lower score unchanged with a prominent warning and expected-failure disclosure. |
| Production could be enabled accidentally | Unauthorized paid sessions | The template and site build default to false; tests cover both outputs. The explicit live controller/site revisions were promoted only after operator approval and a public rollout/cancel/delete smoke. Rollback revisions remain identified. |
