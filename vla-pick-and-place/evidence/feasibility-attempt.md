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
