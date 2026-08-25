# Paid feasibility allocation attempt

Attempted 2026-08-23 at 22:40 PDT after the Task 4 preflight passed and the
operator approved the single temporary feasibility allocation.

## Result

**BLOCKED before allocation.** The official RunPod REST API rejected the one
authorized create request with HTTP 500:

```json
{"error":"create pod: There are no instances currently available","status":500}
```

The request selected exactly the approved resources:

- Secure Cloud;
- one `NVIDIA A100-SXM4-80GB` in `US-KS-2`;
- private template `e56b2xl1y1` and immutable image digest
  `sha256:49c2a30a8fd7c88c3db0c21a18d4df785bf692affde06f2d9527b4e25ae28595`;
- network volume `68s0bxbv7p` mounted at `/models`; and
- non-interruptible execution with no GPU or datacenter fallback.

The Pods collection was empty immediately before and immediately after the
request. RunPod returned no Pod ID, so no container started, no GPU compute was
allocated, and there was no Pod to delete. The private capability and Hub token
were never printed or written to this evidence record.

## Gate decision

Task 5 remains blocked on Secure Cloud A100 SXM capacity. No retry, fallback
GPU, second Pod, checkpoint download, model load, rollout, proxy test, or
cancellation test was attempted. Tasks 6–8 remain blocked because the Task 5
real-checkpoint feasibility gate did not pass.

The safe resume point is the Task 5 allocation step after RunPod reports
capacity for the already-approved A100/volume/datacenter combination. Before
any future create request, verify a positive balance, zero existing Pods, the
same immutable template/image/volume, and live A100 capacity again.

Production live sessions remain disabled and unauthorized.

## Approved US-MD-1 resume

On 2026-08-24, after a read-only inventory comparison, the operator explicitly
approved one fresh A100 SXM 80 GB attempt in `US-MD-1`. Live catalog inventory
reported `Medium` stock there at $1.59/hour, compared with `Low` stock for the
failed `US-KS-2` location. The resume requires a new colocated 20 GB network
volume and a complete fresh preflight before Pod creation. It does not authorize
a different GPU, repeated create attempts, or production live sessions.

## US-MD-1 infrastructure result

Preflight and provisioning were attempted 2026-08-24 at 07:04 PDT.

| Check | Result | Evidence |
| --- | --- | --- |
| Balance and current spend | PASS | Official RunPod CLI reported balance $22.0474149943, current spend $0.002/hour, and spend limit $80. |
| Active Pods | PASS | Official REST list returned zero Pods before provisioning and again after the failure. |
| Exact GPU | AVAILABLE/LOW | Official CLI reported one Secure Cloud `NVIDIA A100-SXM4-80GB` in `US-MD-1` at $1.59/hour with `Low` stock. |
| Checkpoint access | PASS | Official `hf download --dry-run` authenticated and resolved nine files totaling 7.5 GB at revision `8e174154ef5f6c60a8da12ae99c303d8963138c1`. |
| Immutable image/template | PASS | Template `e56b2xl1y1` retained the private registry auth and exact image digest `sha256:49c2a30a8fd7c88c3db0c21a18d4df785bf692affde06f2d9527b4e25ae28595`; Artifact Registry resolved the same digest. |
| US-MD-1 volume | **BLOCKED** | `POST /v1/networkvolumes` for a 20 GB `US-MD-1` volume returned HTTP 500 and no volume ID. The authoritative volume list afterward contained only the existing `US-KS-2` volume. |

No Pod create request was made, no GPU compute was allocated, and no new
volume exists to delete. The existing `US-KS-2` volume remains unchanged.
Task 5 is still blocked before paid compute because a network volume cannot be
attached across datacenters and the approved `US-MD-1` prerequisite could not
be provisioned. No automatic volume retry, Pod retry, or fallback was made.

## Approved H100 NVL recovery

On 2026-08-24 the operator explicitly approved exactly one Secure Cloud
`NVIDIA H100 NVL` 94 GB allocation request in `US-KS-2`. This path reuses
existing volume `68s0bxbv7p`, the immutable image and template, and the exact
checkpoint bootstrap. It replaces the blocked A100/`US-MD-1` path without
authorizing a fallback GPU, repeated create request, longer lifetime, larger
budget, or production live sessions.

## H100 NVL preflight result

The final authenticated preflight on 2026-08-24 blocked before allocation.

| Check | Result | Evidence |
| --- | --- | --- |
| Balance and current spend | PASS | Official RunPod CLI reported balance $22.0474149943, current spend $0.002/hour, and spend limit $80. |
| Active Pods | PASS | Official REST list returned zero Pods. |
| Existing checkpoint volume | PASS | Volume `68s0bxbv7p` remained 20 GB in `US-KS-2`; authenticated S3 listing confirmed the six staged revision/config/processor objects and no model weight, as expected before same-Pod bootstrap. |
| Immutable image/template | PASS | Template `e56b2xl1y1` retained the exact private image digest, registry auth, bootstrap command, and gateway port. |
| Checkpoint access | PASS | Official `hf download --dry-run` resolved the exact nine-file, 7.5 GB snapshot at the accepted revision. |
| Daily Pod billing | PASS | The official billing endpoint returned zero Pod billing records for the current UTC day. |
| H100 NVL capacity | **BLOCKED** | Authenticated RunPod CLI reported Secure Cloud `NVIDIA H100 NVL` with 94 GB at $3.19/hour, but its `US-KS-2` stock status was `none`. |

No Pod-create request was sent because the required exact GPU was unavailable.
Zero Pods remain, no GPU compute was allocated, and no deletion was necessary.
Task 5 and every later paid/deployment task remain blocked.

- [RunPod Pod create API](https://docs.runpod.io/api-reference/pods/POST/pods)
- [RunPod Pod list API](https://docs.runpod.io/api-reference/pods/GET/pods)

## RTX PRO 4500 Blackwell Server Edition attempt

The operator approved exactly one 32 GB `NVIDIA RTX PRO 4500 Blackwell Server
Edition` request in `US-KS-2` after inference-specific checkpoint sizing and a
US-only inventory review. The final preflight passed and the one create request
succeeded; no retry or fallback request was sent.

| Field | Evidence |
| --- | --- |
| Pod | `1m8xyqandczzdb`, `robium-vla-feasibility-4500-20260824` |
| Allocation | Secure Cloud, `US-KS-2`, exact GPU ID above, one GPU, `$0.72/hour` |
| Image | Exact private digest `sha256:49c2a30a8fd7c88c3db0c21a18d4df785bf692affde06f2d9527b4e25ae28595` |
| Volume | `68s0bxbv7p`, 20 GB, colocated and attached in `US-KS-2` |
| Lifetime controls | Created `2026-08-24T14:28:51Z`; provider termination set to `2026-08-24T14:48:49Z`; explicit deletion began `2026-08-24T14:30:47Z` |
| Image startup | First application trace at `2026-08-24T14:30:12Z`, approximately 81 seconds after allocation |
| Result | **FAILED BEFORE CUDA**: `KeyError: 'getpwuid(): uid not found: 65532'` while PyTorch initialized its Inductor cache through `getpass.getuser()` |
| Checkpoint | Bootstrap did not run; post-deletion S3 listing still contained only the six staged metadata/processor objects and no `model.safetensors` |
| Cleanup | Official delete returned `{"deleted": true}`; authoritative Pod list then contained zero matching Pods |
| Cost | Runtime was under two minutes, an upper bound below `$0.024`; account balance was unchanged immediately after deletion, and a later authenticated billing recheck still contained no 2026-08-24 Pod record |

The immutable image declared `USER 65532:65532` without creating that user in
`/etc/passwd`. Importing `torchvision` reached PyTorch Dynamo/Inductor, which
calls `getpass.getuser()` and failed before `torch.cuda` availability, device,
memory, checkpoint load, rollout, proxy, or cancellation could be measured. The
requested create-time command override also did not appear in the returned Pod
details; the image's gateway entrypoint ran instead of the intended
compatibility-first command. A future attempt must not rely on that override.

Free remediation added a real `robium` user/group at UID/GID 65532 and a
writable `/tmp` home to both runtime targets. The old CPU image reproduced the
missing-passwd failure (`getent passwd 65532` exit 2); the rebuilt CPU image
returned `robium:x:65532:65532::/tmp:/usr/sbin/nologin`, Python resolved
`getpass.getuser()` to `robium`, all 17 tests and fake smoke passed, and the
protected container rollout/shutdown lifecycle passed. The same user-creation
command was verified directly against the pinned CUDA runtime base.

At that point no fixed GPU image had been published and no second Pod was
authorized. The operator later accepted continued use of the Hub credential and
authorized the bounded retry documented below.

## Corrected same-Pod feasibility retry

The corrected flow was made self-contained because RunPod had ignored the
earlier request-time command override. The immutable image now creates the
numeric runtime user, runs CUDA compatibility before any checkpoint download,
bootstraps and validates the exact revision only when absent, executes one
measured feasibility episode, and then starts the offline gateway on the same
Pod for proxy and cancellation checks. Red/green startup tests increased the
free suite from 17 to 20 tests.

Cloud Build `6b7bee99-33da-4fc7-96f2-eced08115344` published the final image:

`us-central1-docker.pkg.dev/robium-prod/robium/vla-pick-and-place@sha256:65eb29edb290952ae46c1244fe77edb5dade83546f75389eb3083866c56cf690`

The final preflight verified balance `$22.0200467055`, `$0.002/hour` existing
volume spend, zero Pods, zero posted 2026-08-24 Pod billing records, `Low` exact
GPU stock in `US-KS-2`, the 20 GB volume, exact Hub revision access, and the
template's immutable image/registry/startup configuration. Two direct REST
create requests were rejected with HTTP 400 and returned no Pod ID; zero Pods
was confirmed after each. RunPod's current inventory ID contains `Server
Edition`, while its REST OpenAPI create enum exposes a shorter canonical ID.
The official CLI handled that provider alias and created the intended hardware;
no fallback GPU or duplicate running Pod was used.

| Field | Evidence |
| --- | --- |
| Pod | `bzu8hoikhpaxzz`, `robium-vla-feasibility-4500-retry-20260824` |
| Allocation | Secure Cloud, `US-KS-2`, exact device reported as `NVIDIA RTX PRO 4500 Blackwell Server Edition`, one 32 GB GPU, `$0.72/hour` |
| Lifetime | Created `2026-08-24T16:14:58Z`; provider termination `2026-08-24T16:34:57Z`; explicit deletion at the 19-minute orchestration limit; authoritative absence confirmed |
| CUDA | **PASS**: driver `580.178.04`, PyTorch `2.10.0+cu128`, CUDA `12.8`, compute capability `12.0`, `sm_120` present, 33,687,797,760 device bytes, minimal CUDA tensor result `6.0` |
| Checkpoint bootstrap | **PASS**: 7,473,096,344-byte model persisted at `16:18:00Z`; exact revision marker `8e174154ef5f6c60a8da12ae99c303d8963138c1` written last at `16:18:32Z`, which occurs only after required-file, byte-size, and SHA-256 validation |
| Measured episode | **FAILED/ABSENT**: no `feasibility.json` or video was produced, so checkpoint/processor load, peak model VRAM, latency, simulator result, proxy, and cancellation are not claimed |
| Control plane | RunPod continued reporting `runtime: null`, uptime zero, and no port while the container was demonstrably writing CUDA/checkpoint evidence to the attached volume; those fields were not reliable startup indicators for this Pod |
| Cost | Account balance fell by `$0.1967332148` during the attempt window; the Pod billing record had not posted at the immediate recheck. Nineteen minutes at `$0.72/hour` gives a conservative compute upper bound of `$0.228`. |

The CUDA preflight object was last written at `16:33:21Z`, after the checkpoint
marker, which is consistent with at least one container restart. Provider logs
were unavailable to the credential (HTTP 403), so the failure after checkpoint
bootstrap cannot honestly be classified as OOM, library incompatibility, or an
application exception. Task 5 therefore remains failed and every later paid,
evaluation, proxy, website, and deployment gate remains blocked. No further Pod
is authorized by this attempt.

- [Final same-Pod image build](https://console.cloud.google.com/cloud-build/builds/6b7bee99-33da-4fc7-96f2-eced08115344?project=902570464351)

## Diagnostics-enabled feasibility retry

After the persistent phase/failure markers passed all free gates, the operator
approved one Cloud Build and one bounded RunPod retry. Cloud Build
`14d84508-a86f-4e0f-8e44-5ea6c5a06b51` published source commit `185fb39` as
the exact private digest:

`us-central1-docker.pkg.dev/robium-prod/robium/vla-pick-and-place@sha256:a9bf3722d5aad660a6b8af518f6372a40e53336eea22541a5f72c18608188f81`

The final preflight verified a `$21.7844034019` balance, the `$80` spend limit,
zero Pods, exact `Low` GPU stock in `US-KS-2`, registry credential
`cmt6r3i1c004cq5uqoj4666yr`, volume `68s0bxbv7p`, and the complete exact
checkpoint snapshot including its 7,473,096,344-byte model and revision marker.

| Field | Evidence |
| --- | --- |
| Pod | `opc5yz6isvxmfr`, `robium-vla-feasibility-diag-20260824-184056` |
| Allocation | Secure Cloud, `US-KS-2`, exact `NVIDIA RTX PRO 4500 Blackwell Server Edition`, one 32 GB GPU, `$0.72/hour` |
| Lifetime | Created `2026-08-24T18:40:56Z`; provider termination `2026-08-24T19:00:56Z`; explicitly deleted immediately after diagnosis and authoritative absence confirmed |
| CUDA | **PASS**: driver `580.178.04`, PyTorch `2.10.0+cu128`, CUDA `12.8`, compute capability `12.0`, `sm_120` present, 33,687,797,760 device bytes, tensor result `6.0` |
| Phase | `model_loading`, `running`, persisted at `2026-08-24T18:45:18.361241Z` |
| Failure | **EXACT**: `EOFError`, `EOF when reading a line`, stage `model_loading`, persisted at `2026-08-24T18:45:22.751144Z` |
| Measured episode | **FAILED/ABSENT**: no feasibility result or video; model load, peak VRAM, latency, simulator result, proxy, and cancellation remain unclaimed |
| Cost bound | About five minutes at `$0.72/hour`, below `$0.06`; the current-day posted Pod billing before allocation was `$0.25523381726816297`, and the exact new charge had not posted at deletion |

The pinned LIBERO source at revision
`8f1084e3132a39270c3a13ebe37270a43ece2a01` creates its config on first import
and calls `input()` to ask whether to customize the dataset path. The headless
container has closed stdin, which explains the exact persisted exception. This
is not evidence of CUDA incompatibility or model OOM.

Free remediation now bakes a deterministic LIBERO config into the GPU image,
sets `LIBERO_CONFIG_PATH=/app/libero-config`, and pins every path to the exact
`/opt/libero` checkout. The full 27-test/fake-smoke gate and a closed-stdin
LIBERO import inside the locally rebuilt Linux/amd64 GPU image pass. No fixed
image has been published and no further Pod is authorized. A separate approval
is required for another Cloud Build and bounded RunPod revalidation.

- [Diagnostics image build](https://console.cloud.google.com/cloud-build/builds/14d84508-a86f-4e0f-8e44-5ea6c5a06b51?project=902570464351)

## Noninteractive-config revalidation

The operator authorized publishing commit `22baf65` and one bounded RunPod
revalidation. A first Cloud Build submission explicitly targeted the
`us-central1` regional pool and failed before build creation because project
quota did not permit `E2_HIGHCPU_32` there. The same committed source was then
submitted to the global pool used by the prior successful builds.

Cloud Build `647c9b11-4a51-4476-a7fd-804f4f780e6b` succeeded and Artifact
Registry independently resolved the same immutable digest:

`us-central1-docker.pkg.dev/robium-prod/robium/vla-pick-and-place@sha256:4399bf1000f245bed455757e6ed7f054f982b0b22a81d6e7c7045a10feba3be0`

The final atomic preflight passed with balance `$21.7272749575`, `$80` spend
limit, zero Pods, `$0.25523381726816297` posted current-day Pod billing, exact
`Low` GPU stock, the existing volume/checkpoint, registry credential, new
template digest, and a fresh evidence prefix.

| Field | Evidence |
| --- | --- |
| Pod | `8r15u991q4duzm`, `robium-vla-feasibility-libero-20260824-194015` |
| Allocation | Secure Cloud, `US-KS-2`, exact `NVIDIA RTX PRO 4500 Blackwell Server Edition`, one 32 GB GPU, `$0.72/hour` |
| Image | Exact corrected digest `sha256:4399bf1000f245bed455757e6ed7f054f982b0b22a81d6e7c7045a10feba3be0` |
| CUDA | **PASS** at `19:41:46Z`: driver `580.178.04`, PyTorch `2.10.0+cu128`, CUDA `12.8`, compute capability `12.0`, `sm_120`, 33,687,797,760 device bytes, tensor result `6.0` |
| Noninteractive config | **PASS**: startup passed the previous first-import `input()` boundary and reached environment construction without `EOFError` |
| Failure | **EXACT** at `19:42:09Z`: `FileNotFoundError` for `/app/.venv/lib/python3.10/site-packages/libero/libero/assets/scenes/libero_tabletop_base_style.xml`, stage `model_loading` |
| Measured episode | **FAILED/ABSENT**: no feasibility result/video; policy inference, peak model VRAM, latency, simulator result, proxy, and cancellation remain unclaimed |
| Cleanup | Explicit delete returned `deleted: true`; authoritative Pod list confirmed zero Pods; protected capability and temporary template files were removed |
| Cost | Balance fell by `$0.0111393037`; the Pod-specific billing record had not posted at the immediate recheck |

Local image inspection confirmed the configuration itself returns `/opt/libero`
paths, but Python imports `libero.libero` from the dependency-installed
`site-packages` distribution. `BDDLBaseDomain` derives its `custom_asset_dir`
from that module's `__file__`, so config paths cannot repair the missing wheel
assets. The pinned checkout already contains the scene XML under
`/opt/libero/libero/libero/assets`; it must become the authoritative import
source, with an image-level assertion for both module origin and asset
existence before another paid run.

No second image build or Pod is authorized by this attempt. Production remains
disabled.

- [Corrected config image build](https://console.cloud.google.com/cloud-build/builds/647c9b11-4a51-4476-a7fd-804f4f780e6b?project=902570464351)

## Interactive single-Pod diagnosis

The operator explicitly approved replacing repeated image cycles with one
interactive RTX PRO 4500 Pod, capped at 60 minutes and `$0.72`. Pod
`kvt2gz619xym9s` used the same immutable image digest, registry credential,
`US-KS-2` volume, exact GPU, and `$0.72/hour` rate. A separate debug template
`7ql9yteiyj` and a volume-backed command mailbox were used because RunPod's SSH
API continued returning `pod not ready` despite successful container execution.

| Gate | Result |
| --- | --- |
| Pinned LIBERO source as import root | **REJECTED**: `/opt/libero` is a namespace-package checkout, so the regular `hf-libero` package in `site-packages` wins import resolution. Installing the older checkout would also introduce an undeclared legacy `gym` dependency while the locked wheel correctly uses Gymnasium. |
| Asset-hydrated locked wheel | **PASS**: copying the pinned checkout's assets into a disposable copy of `hf-libero==0.1.4` resolved `libero_tabletop_base_style.xml` while retaining the locked code. CUDA remained available on `NVIDIA RTX PRO 4500 Blackwell Server Edition`. |
| Exact task environment | **PASS**: task 8 resolved to `put_the_bowl_on_the_plate`; EGL reset returned a 256×256 frame and policy keys `pixels` and `robot_state`. |
| Direct network-volume model load | **FAILED/STALLED**: LeRobot found and memory-mapped the 7,473,096,344-byte state dict but did not complete non-sequential remapping reads from the network volume. |
| Transient container-disk model load | **PROGRESSED**: a sequential copy to `/tmp` completed and model loading advanced immediately. The pinned LeRobot loader then reported its strict tied-embedding alias mismatch; application loading must use `strict=False` and verify shared embedding/head storage explicitly. |
| Offline processor load | **BLOCKED**: the checkpoint preprocessor requires `google/paligemma-3b-pt-224`, but the persistent snapshot contains no tokenizer artifacts. With offline mode enabled, `AutoTokenizer` failed exactly because the files were not cached. |
| Gated tokenizer access | **BLOCKED**: authenticated model metadata resolved immutable revision `35e4f46485b4d07967e7e9935bc3786aad50687c`, but direct download of the tokenizer returned HTTP 403. The configured account therefore lacks the manually gated PaliGemma access grant required by the paid-gate preflight. |
| Episode, proxy, cancellation | **NOT RUN**: licensing failed before these gates. No success, latency, VRAM, proxy, or cancellation claim is made. |
| Cleanup | **PASS**: the Pod was explicitly deleted, the debug template was deleted, and authoritative APIs returned zero Pods and no matching template. The checkpoint volume was preserved. |
| Cost | Balance moved from `$21.7016906538` before allocation to `$21.2831552835` after cleanup, a conservative observed-window delta of `$0.4185353703`, below the approved `$0.72` cap. The Pod-specific billing row had not posted at the immediate recheck. |

Free remediation hydrates the locked wheel's assets at image build time, pins
and validates the five tokenizer artifacts as a second snapshot, overrides the
offline tokenizer path, stages the verified checkpoint to transient container
disk before model mmap, and validates tied embedding storage after non-strict
loading. The asset-hydration Linux/amd64 GPU packaging revision built locally as manifest
`sha256:5c305881e352bcbf48ecea256e425f5c2fe42bbb1b104fdbdb8726de467b7104`;
with closed stdin it imported the locked wheel from `site-packages`, found the
hydrated scene XML, reset exact task 8 under EGL, and returned a 256×256 frame.
The subsequent same-source/target staging guard is covered by the 33-test free
suite; a redundant local CUDA-builder re-download was cancelled before export.
No new immutable image has been published, because direct tokenizer access must
pass before the next paid gate. Production remains disabled.

## Gated-tokenizer access recheck

On 2026-08-24, after the operator accepted the PaliGemma terms for the account
associated with the Doppler `HF_TOKEN`, a free authenticated download passed
for all five required tokenizer files at exact revision
`35e4f46485b4d07967e7e9935bc3786aad50687c`:

| File | Downloaded bytes |
| --- | ---: |
| `added_tokens.json` | 24 |
| `special_tokens_map.json` | 607 |
| `tokenizer.json` | 17,549,604 |
| `tokenizer.model` | 4,264,023 |
| `tokenizer_config.json` | 39,968 |

The disposable download was moved to macOS Trash after validation. This clears
the Hugging Face licensing preflight only; it does not claim model loading or
episode success. No Cloud Build or RunPod Pod was started, and production
remains disabled. The next gates are a separately approved paid immutable-image
publish followed by one bounded RunPod revalidation.

## Tokenizer-enabled immutable-image revalidation

The operator approved one Cloud Build and one bounded RTX PRO 4500 SE Pod.
Free preflight passed doctor, 33 tests, fake smoke, Ruff lint/format, both exact
Hub revision range requests, positive balance, zero Pods, exact GPU stock, the
existing volume, registry credential, and template configuration.

- [Cloud Build `ce81dcc0-6ec9-4121-bfa8-82b9f552c46a`](https://console.cloud.google.com/cloud-build/builds/ce81dcc0-6ec9-4121-bfa8-82b9f552c46a?project=902570464351)
- immutable image digest:
  `sha256:910848b3917685643062a405629228271e531c0ce087b9e96cc091449686e560`
- Pod `17h7vt1fjf9fzr`, Secure Cloud `US-KS-2`, exact NVIDIA RTX PRO
  4500 Blackwell Server Edition, `$0.72/hour`, provider termination set 20
  minutes after creation

| Gate | Result |
| --- | --- |
| CUDA | **PASS**: driver `580.178.04`, PyTorch `2.10.0+cu128`, CUDA `12.8`, compute capability `12.0`, `sm_120`, 33,687,797,760 device bytes, tensor result `6.0` |
| Tokenizer/bootstrap/staging | **PASS**: startup advanced through the exact-revision tokenizer bootstrap and local checkpoint staging to `model_loading` |
| Real model load | **PASS TO FIRST ROLLOUT**: startup advanced from `model_loading` to the measured `rollout` stage without a model-load failure |
| Measured episode | **FAILED** before the first action: `ValueError: _quat2axisangle expected shape (B, 4), got (4,)` |
| Proxy/cancellation | **NOT RUN**: the mandatory measured episode gate failed first |
| Cleanup | **PASS**: explicit delete returned `deleted: true`; authoritative Pod listing returned zero immediately |
| Cost | balance moved from `$21.2812108391` to `$21.2300175576`, an observed-window delta of `$0.0511932815`; only the existing `$0.002/hour` volume spend remained |

Pinned-source inspection identifies a vectorization seam: the application uses
one direct `LiberoEnv`, whose nested quaternion is unbatched `(4,)`, while the
pinned LeRobot `LiberoProcessorStep` accepts only vector-environment shape
`(B, 4)`. No second build or Pod is authorized. Production remains disabled.

## Interactive same-Pod fix validation

The operator approved one 60-minute interactive allocation so the remaining
application/image seams could be diagnosed without repeated immutable builds.
Pod `ania2yd8fdkasy` used the same exact image digest, Secure Cloud `US-KS-2`,
private volume, and exact RTX PRO 4500 Blackwell Server Edition at `$0.72/hour`.
All source corrections were made and tested locally, then overlaid into this
single disposable Pod for validation; the overlay is not presented as the
final immutable image.

| Gate | Result |
| --- | --- |
| Direct-LIBERO batch seam | **PASS**: raw quaternion `(4,)` became `(1, 4)` at the adapter boundary and pinned processing produced state `(1, 8)` on CUDA |
| Real offline episode | **PASS**: state `0`, seed `1000`, simulator success `true`, 75 steps, 76 frames, 3.6926 s rollout, 41.0438 s model startup, 7,647,661,056 peak allocated VRAM bytes |
| Latency | mean 25.3068 ms, p95 155.6385 ms, max 361.1389 ms |
| Video evidence | **PASS** after converting Pillow frames to arrays: 113,024-byte MP4, SHA-256 `19058130c508ab6828ef98a1d5bc7e868c176ede39780b1613ed3730f5c6d03f` |
| Proxy isolation | **PASS** through `*.proxy.runpod.net`: root 404, foreign capability 404, scoped UI 200, claim/status 200 |
| Cancellation | **PASS** in a separate non-measured rollout: status reached `running`, cancel returned `cancelling: true`, result returned `cancelled: true`, `steps: 0`, and final phase `ready` |
| Compile-path diagnosis | The pinned policy's default `torch.compile` path failed because the runtime lacked a C compiler. A diagnostic `TORCHDYNAMO_DISABLE=1` proved the remaining model/simulator path; the final Dockerfile adds `gcc` and `python3.10-dev` instead of shipping the diagnostic bypass. |
| Cleanup | **PASS**: evidence downloaded, Pod deleted, authoritative listing returned zero Pods, temporary debug template deleted, and exact temporary S3 prefix removed; persistent model volume preserved |
| Cost | Balance moved from `$21.2300175576` before the interactive allocation to `$20.8771312613` after cleanup, an observed-window delta of `$0.3528862963`; only the existing `$0.002/hour` volume spend remained |

The free post-fix gate passes 35 tests, doctor, fake smoke, Ruff lint/format,
and diff checks.

## Compiler-bearing immutable image

Global Cloud Build `3829dc62-c144-4956-a8a0-0d2eb14c02c3` built committed app
source `c29e7ba8023bc20bb92ab9285b351e8abd8a236c` and pushed:

`us-central1-docker.pkg.dev/robium-prod/robium/vla-pick-and-place@sha256:0bc3bae587da9c175f8bce667009bfb3103251e75b11898ae8666c58ec61f083`

Artifact Registry independently resolved the tag to the same digest. Private
RunPod template `e56b2xl1y1` was updated to that exact digest and re-read with
`VLA_LIVE_ENABLED=false`, `VLA_RUNTIME_MODE=real`, and
`VLA_STARTUP_MODE=feasibility`. The authoritative Pod list remained empty; no
production or validation Pod was started during deployment.

- [Compiler-bearing Cloud Build](https://console.cloud.google.com/cloud-build/builds/3829dc62-c144-4956-a8a0-0d2eb14c02c3?project=902570464351)

## Final immutable-image revalidation

The operator approved one bounded validation of the exact deployed digest on
2026-08-24. Two RunPod creation paths silently failed the storage contract
before the successful allocation. Pod `0qnawrzk6nzb63`, created from the
template with `runpodctl` v2.8, eventually entered a restart loop after a long
cold pull; the supplied system logs repeatedly showed
`PermissionError: [Errno 13] Permission denied: '/models'`. RunPod's API
reported `networkVolume: null`. A second CLI allocation,
`q52n2195u9a1ed`, accepted explicit network-volume and mount flags but again
reported `networkVolume: null`, so it was deleted before startup. Direct REST
creation could not express the inventory's exact `NVIDIA RTX PRO 4500
Blackwell Server Edition` identifier because the current REST enum only
accepted the non-Server-Edition name.

Official GraphQL `podFindAndDeployOnDemand` then created Pod `aujvvs0earwm5l`
with `networkVolumeId: 68s0bxbv7p`, `volumeInGb: 0`, mount path `/models`, the
exact Server Edition GPU, registry credential, and immutable digest. The
GraphQL response and a follow-up read both confirmed the attached 20 GB
`US-KS-2` network volume.

| Gate | Result |
| --- | --- |
| Exact image | **PASS**: `us-central1-docker.pkg.dev/robium-prod/robium/vla-pick-and-place@sha256:0bc3bae587da9c175f8bce667009bfb3103251e75b11898ae8666c58ec61f083` |
| CUDA | **PASS**: RTX PRO 4500 Blackwell Server Edition, PyTorch `2.10.0+cu128`, CUDA `12.8`, compute capability `12.0`, 33,687,797,760 device bytes, tensor result `6.0` |
| Default compile path | **PASS**: no `TORCHDYNAMO_DISABLE` override; model startup 57.6298 s |
| Real offline episode | **PASS**: state `0`, seed `1000`, success `true`, 75 steps, 76 frames, 291.9145 s total, 7,691,964,928 peak allocated VRAM bytes |
| Latency | mean 3,788.5189 ms, p95 251.8201 ms, max 281,065.3675 ms; the first compiled action dominates the mean and max |
| Video evidence | **PASS**: SHA-256 `a05ab41731ee300366aa5ef849a8e446359fb33af385dee74e53e66e871e9610`, independently matched after download |
| Proxy isolation | **PASS**: root 404, foreign capability 404, scoped UI 200, claim/status ready |
| Cancellation | **PASS** on separate state `2` rollout: reached running, cancel returned `cancelling: true`, result returned `cancelled: true`, `success: null`, `steps: 0`, `frame_count: 1`, final status ready |
| Cleanup | **PASS**: all three temporary Pods deleted, authoritative Pod count zero, temporary S3 evidence prefixes empty, persistent checkpoint volume preserved |
| Cost | Balance moved from `$20.8771312613` before this validation block to `$20.3156361353` after cleanup, an observed-window delta of `$0.5614951260` including the two failed allocations; only the persistent volume's `$0.002/hour` spend remained |

The private template remains pinned to the validated digest with
`VLA_LIVE_ENABLED=false`. The next paid gate is the issue's exact 20-episode
public evaluation and evidence publication. Production live sessions remain a
separate operator approval and were not enabled.

RunPod API references used during recovery:

- [Pod create REST API](https://docs.runpod.io/api-reference/pods/POST/pods)
- [GraphQL Pod management](https://docs.runpod.io/sdks/graphql/manage-pods)
- [RunPod GraphQL schema](https://graphql-spec.dev.runpod.io/)
