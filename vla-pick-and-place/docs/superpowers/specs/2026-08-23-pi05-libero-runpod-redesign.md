# Pi0.5 LIBERO VLA Pick-and-Place Redesign

**Date:** 2026-08-23

**Status:** Approved by [Robium issue #69](https://github.com/robium-ai/robium/issues/69)

**Owners:** `robium-ai/robium-apps` owns the application, evaluation harness,
evidence schema, gateway, and GPU image. `robium-ai/robium-website` owns the
article, live workspace, provider routing, RunPod lifecycle, budget enforcement,
and production deployment. `robium-ai/robium` receives only dated learnings; no
Robium skill changes are in scope.

## Goal

Replace the active SmolVLA/SO-101 experiment in `vla-pick-and-place` with an
honest, reproducible Pi0.5 evaluation and optional live demonstration:

- the official `lerobot/pi05_libero_finetuned_v044` checkpoint;
- the Franka Panda in zero-based LIBERO-Goal task 8,
  `put_the_bowl_on_the_plate`;
- one complete autonomous rollout at a time;
- simulator-derived success, streamed simulator frames, and measured timings;
- a public, immutable 20-episode evidence bundle; and
- a capability-isolated RunPod Pod that remains disabled in production until
  separately approved.

This is not a training project. The app links to upstream LeRobot training
guidance and contains no Robium training wrapper. It also has no local Apple
Silicon inference path. Local development exercises configuration, fixtures,
fake-policy rollouts, replay, UI, publication validation, and lifecycle tests.

## Verified upstream inputs

The implementation pins these directly verified revisions:

| Input | Immutable revision | Verification |
| --- | --- | --- |
| Pi0.5 checkpoint | `8e174154ef5f6c60a8da12ae99c303d8963138c1` | Hugging Face model API; the snapshot contains weights plus pre/postprocessor files. |
| LeRobot v0.4.4 | `8fff0fde7c79f23a93d845d1a50e985de01f8b8a` | Git tag and source inspection. |
| LIBERO | `8f1084e3132a39270c3a13ebe37270a43ece2a01` | Upstream `master` commit and task-map inspection. |
| CUDA builder image | `nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04@sha256:622e78a1d02c0f90ed900e3985d6c975d8e2dc9ee5e61643aed587dcf9129f42` | Docker Hub tag API. |
| CUDA runtime image | `nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04@sha256:2fcc4280646484290cc50dce5e65f388dd04352b07cbe89a635703bd1f9aedb6` | Docker Hub tag API. |

The LIBERO task map at the pinned revision identifies task 8 as
`put_the_bowl_on_the_plate`. LeRobot's v0.4.4 LIBERO environment provides a
seven-dimensional continuous action space, main and wrist RGB observations,
fixed official initial states, sparse simulator success, and a 300-step default
for LIBERO-Goal. The official LeRobot reproduction uses `n_action_steps=10`,
batch size 1, synchronous evaluation, and EGL on headless Linux; this app keeps
those mechanics while restricting evaluation to task 8.

## Selected architecture

### Application process

One Python process owns the complete rollout failure domain:

1. `LiberoTask` resolves only suite `libero_goal` and task ID 8 and verifies the
   upstream task name before any rollout.
2. `InitialStateCatalog` exposes three curated official initial-state IDs: 0,
   1, and 2. Their names are stable UI identifiers, not generated scenes.
3. `Policy` has two implementations behind one protocol:
   `Pi05PolicyAdapter` for CUDA and `DeterministicFakePolicy` for free tests.
4. `RolloutRunner` hard-resets the environment, selects one fixed official
   state, applies the prompt, streams nonblank RGB frames and progress, and
   takes the final result only from LIBERO's simulator success signal.
5. `EpisodeLock` permits one rollout at a time and provides cooperative
   cancellation. Cancellation never converts an incomplete episode into a
   measured failure or success.
6. `EvidenceWriter` records timings, configuration, result, video, and hashes
   without accepting aggregate claims from callers.
7. `Gateway` exposes capability-scoped claim, status, shutdown, Gradio UI, and
   streaming routes on one public port.

The policy and simulator stay in the same process. Their observations and
actions are high-rate, same-host data with one shared failure domain; splitting
them would add serialization and another secret-bearing service without a
useful independent restart boundary. The website orchestrator is lifecycle-only
and leaves the frame/action path after returning the private Pod host.

### Prompt contract

The exact canonical prompt is `put the bowl on the plate`.

- An exact match after trimming outer whitespace is `benchmark-supported`.
- Any edited nonempty prompt is `experimental`.
- Prompts are limited to 200 Unicode code points, matching the checkpoint's
  tokenizer limit.
- Rendering always treats prompt text as text, never HTML.
- Edited prompts exist only in Pod memory and are discarded with the Pod.
- Edited prompts, observations, and visitor videos are never logged or stored.

The benchmark label is a provenance claim, not a promise of success. The live
UI always shows which class is active.

### Local and container environments

The committed application uses one uv lock and a multi-stage Linux/amd64 CUDA
image. The image pins the base-image digests above, LeRobot and LIBERO commits,
Python 3.10, dependency resolution, and the application source. `MUJOCO_GL=egl`
is mandatory for real headless simulation.

The GPU image does not bake checkpoint weights. By explicit user approvals on
2026-08-23 and 2026-08-24, the one successfully allocated feasibility Pod may
populate its attached `US-MD-1` private RunPod network volume from the exact
checkpoint revision. The
feasibility-only bootstrap removes any stale revision marker, downloads config,
weights, preprocessor JSON/safetensors, and postprocessor JSON/safetensors,
verifies the 7,473,096,344-byte model SHA-256
`877b3ec1130548b69af7f8aeef3ec9d3fc7738040f0b9beb490857ec970997ae`,
validates every required file, and writes the exact revision marker atomically
as the final step. It then removes `HF_TOKEN` from child-process environment,
enables Hub and Transformers offline settings, and runs feasibility. Later
visitor starts are offline-only and fail before readiness on any mismatch,
drift, or missing weights or processor files.

Local macOS never loads Pi0.5. It runs the same rollout coordinator, gateway,
Gradio app, evidence schema, and fixed-state mapping with the fake policy and
small recorded RGB fixtures. The CPU container gateway smoke uses this same fake
mode, so it can pass before any paid GPU is allocated.

## Evaluation and evidence

### Feasibility gate

Paid work begins only after all local tests and the CPU/fake-policy container
gateway smoke pass. By explicit user amendment on 2026-08-23, the paid
feasibility run must use exactly one Secure Cloud NVIDIA A100 SXM with 80 GB
VRAM in `US-MD-1`, verified again by the live provisioning API to support
network volumes and by the S3 API to support direct access. This replaces the
original A40/A6000 model-name restriction without changing the single-Pod
limit, budget, or validation gates. It performs:

1. one-time exact-revision checkpoint bootstrap onto the attached volume,
   followed by token-free offline checkpoint and processor load on the same
   Pod;
2. one hard-reset task-8 rollout at batch size 1;
3. measurement of image pull, process/model startup, peak VRAM, per-action
   latency, Pod proxy behavior, and cancellation;
4. simulator-derived result capture; and
5. Pod deletion followed by an API check that the Pod is absent.

There is no fallback feasibility Pod, quantization, model surgery, or
launch-time memory optimization. The 2026-08-23 `US-KS-2` create request
returned no Pod ID and allocated no compute. On 2026-08-24 the operator
explicitly amended the design to authorize one fresh `US-MD-1` allocation
attempt with a new colocated volume; this is not permission for repeated
allocation retries. Bootstrap, validation, or offline-load failure deletes the
Pod and blocks the 20-episode evaluation.

### Twenty-episode protocol

The publication run is one sequential process, batch size 1, with no retries for
headline improvement:

- suite `libero_goal`, task ID 8;
- canonical prompt only;
- 20 fixed official initial states, IDs 0 through 19, one per episode, mapped
  to simulator seeds 1000 through 1019 by episode index;
- hard environment and policy reset before every episode;
- at most 300 simulator steps per episode;
- `n_action_steps=10`; and
- exact checkpoint, LeRobot, LIBERO, application commit, and image digest.

The target is at least 16 successes. Any technically valid lower result is
published unchanged with a prominent below-target warning.

### Evidence layout

Git contains only compact publication media and metadata:

```text
evidence/
  manifest.schema.json
  manifest.json
  results.md
  previews/
    state-0.webp
    state-1.webp
    state-2.webp
```

The public Hugging Face dataset contains all 20 MP4 videos, per-episode JSON,
the same manifest, and a README. The manifest is the source of truth and stores:

- schema version and immutable Hugging Face dataset revision;
- aggregate success count, total episodes, target, and below-target flag;
- every episode's task, seed, fixed-state ID, prompt class, success flag,
  duration, step count, action-latency statistics, video path, and SHA-256;
- checkpoint, LeRobot, LIBERO, app commit, image digest, GPU, and RunPod cost;
- reproduction command plus serialized configuration; and
- SHA-256 for every published artifact.

Validation rejects zero episodes, any count other than 20 for a publication
manifest, duplicate episode/state mappings, mismatched aggregate counts,
missing or incorrect hashes, mutable revisions, and configuration drift.

## Gateway and capability isolation

The Pod gateway binds the configured port and mounts every route below an
unguessable capability prefix:

```text
/c/{capability}/claim
/c/{capability}/status
/c/{capability}/shutdown
/c/{capability}/ui/
/c/{capability}/stream/...
```

The capability is generated by the orchestrator, injected as a secret
environment value, and returned only to the allocating browser. Missing,
malformed, or foreign capabilities receive 404 without disclosing whether a Pod
exists. The gateway's root and unrelated routes also return 404. Gradio is
mounted with its root path set to the capability prefix so its assets, API, and
stream requests cannot escape the protected path.

Claim is idempotent for the owning capability. Status returns only operational
phase, coarse timing, selected public state identifier, prompt class, and
simulator outcome. Shutdown responds before terminating the process. Neither
browser payloads nor logs contain RunPod or Hugging Face credentials.

## RunPod provider

### Provider routing

Demo configuration gains `provider: cloud-run | runpod` plus a RunPod block.
Local mode still resolves every demo to `LocalDockerDriver`. Production uses a
`ProviderRouter`: existing demos continue through `CloudRunDriver`; only
`vla-pick-and-place` goes through `RunPodDriver`.

Service records add provider and the complete human-readable phases:
`disabled`, `busy`, `allocating`, `booting`, `ready`, `stopping`, `failed`,
`budget-exhausted`, and `expired`. Existing phases retain their behavior and are
mapped without changing current Cloud Run or local Docker contracts.

### Pod ownership and provisioning

Every VLA Pod:

- uses the dedicated immutable private image and RunPod template;
- has a `robium-vla-{session}` name plus the dedicated template/cost-center
  association;
- requests exactly one GPU from the allowlist `NVIDIA A100-SXM4-80GB`, never a
  smaller or different fallback;
- runs in `US-MD-1` and attaches the configured colocated checkpoint volume at
  `/models`;
- exposes only the configured HTTP gateway port;
- receives capability, expiry, checkpoint path, and non-secret runtime config;
- receives no Hugging Face token during normal visitor startup; and
- is deleted, never stopped, on visitor stop, expiry, boot failure, hard
  timeout, or reconciliation cleanup.

RunPod API and registry credentials live only in orchestrator secret bindings.
The driver lists all Pods but reconciles only Pods whose name prefix and template
ID both match. It never mutates unrelated resources.

### Lifetimes and concurrency

- maximum active VLA Pods: 1;
- boot timeout: 8 minutes;
- ready window: 10 minutes;
- absolute lifetime from allocation: 20 minutes;
- one rollout at a time within the ready window; and
- no waiting queue or queue database.

A busy request receives a readable state, keeps recorded evidence visible, and
offers manual retry.

### Daily budget

The UTC-day allowance is $5. Before allocation, the provider atomically checks:

1. RunPod `/billing/pods` usage for every owned Pod ID recorded for the current
   UTC day;
2. active owned Pods and their API-reported adjusted hourly rates;
3. unexpired reservations at a conservative 20-minute lifetime; and
4. the candidate Pod's conservative requested-GPU rate.

Owned Pod IDs, reservations, actual adjusted rate, creation/deletion time, and
final billed amount are stored in a small durable GCS budget ledger guarded by
object-generation preconditions. This is not a session queue. Allocation fails
closed as `budget-exhausted` if billing, active-Pod, ledger, rate, or atomic
reservation verification fails, or if billed plus reserved cost would exceed
$5. The dedicated RunPod cost center remains the operator-facing attribution
view; the ledger supplies the Pod-ID mapping that RunPod's billing API omits
after deletion.

## Website and article

The VLA page becomes a robotics-engineer-oriented article plus proof workspace.
It remains useful in every runtime state:

- the immutable result and recorded runs are always visible;
- three curated state previews show their measured canonical-prompt outcomes;
- LeRobot's published 97.5% four-suite result is clearly attributed and never
  presented as Robium's score;
- Robium's own 20-episode task-8 result comes only from the manifest;
- a score below 16/20 displays a prominent warning;
- disabled, busy, budget-exhausted, unavailable, and failed states preserve the
  article and manual retry; and
- production deployed with `VLA_LIVE_ENABLED=false` explicitly says live GPU
  sessions are disabled.

The live workspace embeds the capability-scoped Pod UI directly at desktop,
tablet, and mobile widths. The orchestrator exits the data path after handoff.

## Validation gates

Gates are executed in this exact order:

1. **Design:** commit this spec and the active architecture brief separately.
2. **Application unit/integration:** fixed-state mapping, prompt classification
   and safety, locking, cancellation, aggregation, manifest schema, hashes,
   zero-episode guard, fake rollout, and nonblank frames.
3. **Application smoke:** fake-policy lifecycle and replay through the real UI.
4. **Container gateway:** build the pinned image's CPU/fake target; verify start,
   capability acceptance/rejection, UI, stream, shutdown, and process exit.
5. **Paid feasibility:** one real A100 SXM 80 GB Pod; no fallback Pod; record
   all required measurements and deletion.
6. **Paid evaluation:** 20 sequential hard-reset episodes; validate and publish
   the immutable evidence dataset.
7. **Website/orchestrator:** mocked RunPod create/get/delete/reconcile, one-Pod
   busy, $5 refusal, all UI phases, responsive embed, local fake end to end, and
   existing demo/site regressions.
8. **Real lifecycle:** start, ready, rollout, result, stop, and confirmed deletion.
9. **Disabled production deployment:** application, evidence, article, and
   provider integration deployed with `VLA_LIVE_ENABLED=false`.
10. **Production enablement:** not authorized by issue #69 implementation.

Any gate failure blocks later paid or production work. Missing credentials,
funding, accepted licensing, private registry, network volume, GPU capacity, or
required infrastructure stops the work before the affected paid gate.

## Rollback and production approval

Rollback is `VLA_LIVE_ENABLED=false` plus reconciliation of expired owned Pods.
Recorded evidence and the article remain available.

Production live sessions are explicitly out of scope. After the maintainer
separately approves the reviewed evidence bundle and real RunPod smoke, the
enablement step is to set `VLA_LIVE_ENABLED=true`, deploy the controller,
exercise one production start-to-deletion lifecycle, and monitor initial session
and budget behavior. No part of this issue grants that approval.
