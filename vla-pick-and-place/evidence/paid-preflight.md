# Paid-gate preflight

Read-only preflight performed 2026-08-23 at 18:49 PDT. No Pod, template,
volume, registry artifact, or other paid resource was created.

| Prerequisite | Result | Evidence |
| --- | --- | --- |
| RunPod API authentication | PASS | Bearer credential listed Pods, templates, network volumes, and Pod billing through the official REST API. |
| Positive RunPod credit balance | **BLOCKED** | The credential's `myself.clientBalance` query returned HTTP 403, so the required positive balance could not be verified. Allocation must fail closed. |
| Existing active Pods | PASS | REST list returned zero Pods. |
| Billing endpoint | PASS | `/v1/billing/pods` returned six historical billing records. |
| Accepted checkpoint/license access | PASS | Official `hf` CLI authenticated as the Robium account and dry-ran all six required files (7.5 GB total) at checkpoint revision `8e174154ef5f6c60a8da12ae99c303d8963138c1`. |
| Private registry authentication | PARTIAL | The authenticated GCP account can read the private `robium-prod/robium` Artifact Registry repository. |
| Immutable VLA GPU image | **BLOCKED** | No `vla-pick-and-place` artifact/digest exists in the private registry. |
| Dedicated RunPod template/cost center | **BLOCKED** | The RunPod template list returned zero templates; no dedicated template or cost-center association can be verified. |
| Preloaded checkpoint network volume | **BLOCKED** | The RunPod network-volume list returned zero volumes, so no exact-revision snapshot or processor files exist to validate. |
| Secure Cloud 48 GB capacity | PASS at check time | Official GraphQL `lowestPrice` query for one Secure Cloud GPU returned A40 48 GB stock `High` and RTX A6000 48 GB stock `Low`, each with a current on-demand rate. |
| Deletion verification path | PASS | Official REST schema exposes `DELETE /pods/{podId}` and `GET /pods/{podId}`; absence can be polled after deletion. No Pod was created to exercise it. |

Authoritative API references:

- [RunPod Pod REST API](https://docs.runpod.io/api-reference/pods/POST/pods)
- [RunPod GPU availability query](https://docs.runpod.io/sdks/graphql/manage-pods#check-gpu-availability)
- [Pinned Pi0.5 checkpoint](https://huggingface.co/lerobot/pi05_libero_finetuned_v044/tree/8e174154ef5f6c60a8da12ae99c303d8963138c1)

## Gate decision

Task 4 fails closed. Tasks 5–8 are blocked by missing/unverifiable funding and
required infrastructure. In particular, no feasibility Pod, A100 fallback,
20-episode evaluation, evidence dataset, RunPod provider deployment, or
production Pod was created. `VLA_LIVE_ENABLED` was not set to true anywhere.

To reopen the gate, an operator must provide and verify all of the following:

1. a RunPod balance visible to the credential and sufficient for the issue budget;
2. a dedicated RunPod template/cost center using the immutable private image;
3. a compatible network volume populated with the exact accepted checkpoint revision and a matching `REVISION` marker; and
4. the immutable private GPU-image digest plus registry authentication usable by RunPod.

## Recheck after funding (2026-08-23 21:36 PDT)

The operator created the dedicated cost center and funded the account. A second
read-only preflight verified `clientBalance` **$22.0668594383**, zero active
Pods, and the successful immutable GPU image:

`us-central1-docker.pkg.dev/robium-prod/robium/vla-pick-and-place@sha256:d0c53a7fb0ccc420fc8320dfd90653b60fc6eb3a75351dc297c85cb87528e927`

Cloud Build `9ab9ef04-c3db-44d2-8525-f7d5a4c1422a` built and published that
digest. The paid gate remains closed for the following infrastructure reasons:

| Prerequisite | Result | Evidence |
| --- | --- | --- |
| Positive RunPod credit balance | PASS | Official `runpodctl user` returned a $22.0668594383 client balance and $0 current hourly spend. |
| Immutable VLA GPU image | PASS | Artifact Registry resolves the image tag to digest `sha256:d0c53a7f...e927`. |
| Dedicated cost center | PARTIAL | The operator confirmed creation, but no template, network volume, or Pod exists to associate with or verify under it. |
| RunPod private-registry auth | **BLOCKED** | The account has no Artifact Registry credential entry for the immutable private image. |
| Preloaded checkpoint network volume | **BLOCKED** | The account has zero network volumes and no separate RunPod S3 API credential (`RUNPOD_S3_ACCESS_KEY` / `RUNPOD_S3_SECRET_KEY`) for Pod-free preload. |
| Compatible volume location and 48 GB capacity | **BLOCKED** | Official `runpodctl gpu list` reported A40 stock only in `CA-MTL-1` (Medium) and `EU-SE-1` (High), and RTX A6000 stock only in `EU-SE-1` (Low) and `US-TX-1` (Low). None is in RunPod's documented S3-compatible network-volume datacenter list. The S3-enabled A40/A6000 locations (`US-MO-1`, `EU-RO-1`, `US-KS-2`) reported stock `none`. |

No RunPod template, volume, registry credential, or Pod was created during the
recheck. In accordance with Task 4, Task 5 paid compute remains blocked until
an allowed 48 GB GPU is stocked in an S3-enabled volume location and the
operator provisions the required Pod-free preload and private-registry
credentials.

Additional authoritative references:

- [RunPod S3-compatible network-volume API](https://docs.runpod.io/storage/s3-api)
- [RunPod network volumes](https://docs.runpod.io/storage/network-volumes)
- [Successful immutable GPU-image build](https://console.cloud.google.com/cloud-build/builds/9ab9ef04-c3db-44d2-8525-f7d5a4c1422a?project=902570464351)

## Alternative-resource recheck (2026-08-23 22:15 PDT)

The operator explicitly broadened the original A40/A6000 restriction. Live
inventory and live volume-provisioning checks selected `NVIDIA
A100-SXM4-80GB` in `US-KS-2`: Secure Cloud stock was `Low`, the current rate
was $1.59/hour, and the datacenter accepted a network-volume create request.
The narrower L40S candidate in `US-MO-1` was rejected because RunPod's live API
reported that datacenter does not currently support network volumes, despite
its appearance in the published S3 endpoint table.

Provisioned prerequisites:

- private registry auth `robium-vla-artifact-registry` for the immutable image;
- 20 GB network volume `68s0bxbv7p` (`robium-vla-pi05-v044`) in `US-KS-2`;
- verified RunPod S3 credentials; and
- six small checkpoint/config/processor files plus the exact `REVISION` marker
  under `pi05-libero-v044/`.

The required 7,473,096,344-byte `model.safetensors` remains blocked. The
official AWS CLI path failed on HTTP 524 during multipart upload. RunPod's
official large-file helper also timed out with 50 MB and 10 MB parts; 5 MB
parts succeeded but measured only about 0.24 MB/s, projecting many hours for
the file. Every failed multipart upload was explicitly aborted and the API
confirmed no open multipart sessions. The remote volume contains no partial
model object.

No Pod was created. The paid compute gate therefore remains closed. The
practical next step requires an explicit amendment to let the same single A100
feasibility Pod populate the attached volume from the immutable Hub revision,
then restart the application with Hub networking disabled and perform the
measured offline load and rollout.

## Approved same-Pod bootstrap preflight (2026-08-23 22:37 PDT)

The operator explicitly approved the narrow amendment above. The application
implements and tests revision-marker-last bootstrap, exact model byte/hash
validation, and token-free offline child processes in commit `8556dac`.
Cloud Build `9ae3b301-28ed-422f-99a7-b9298f216f09` published the resulting
image:

`us-central1-docker.pkg.dev/robium-prod/robium/vla-pick-and-place@sha256:49c2a30a8fd7c88c3db0c21a18d4df785bf692affde06f2d9527b4e25ae28595`

| Prerequisite | Result | Evidence |
| --- | --- | --- |
| Balance and current spend | PASS | Official `runpodctl user` reported balance $22.0649149939, current spend $0.002/hour, and spend limit $80. |
| Active Pods | PASS | Official REST list returned zero Pods. |
| Checkpoint/license access | PASS | Official `hf` CLI authenticated as the Robium account and dry-ran the exact 7.5 GB model at revision `8e174154...138c1`. |
| Immutable private image | PASS | Private template `e56b2xl1y1` references digest `sha256:49c2a30a...28595` and registry auth `cmt6r3i1c004cq5uqoj4666yr`. |
| Checkpoint volume | PASS under approved amendment | Volume `68s0bxbv7p` is 20 GB in `US-KS-2`; six exact processor/config files are staged. The same one feasibility Pod will download and hash the model, write `REVISION` last, remove the Hub token from child processes, and load offline. |
| Secure Cloud capacity | PASS at check time | `NVIDIA A100-SXM4-80GB` in `US-KS-2` reported stock `Low` at $1.59/hour. |
| Billing and deletion paths | PASS | Billing returned six historical records; REST exposes Pod delete and absence polling. |
| Free gates | PASS | `make check`: doctor, 17 tests, and deterministic fake smoke passed. |

Task 4 passes under the explicit same-Pod bootstrap amendment. Exactly one
temporary A100 feasibility Pod is authorized next. Production live sessions
remain disabled and unauthorized.

- [Successful bootstrap image build](https://console.cloud.google.com/cloud-build/builds/9ae3b301-28ed-422f-99a7-b9298f216f09?project=902570464351)

## RTX PRO 4500 Blackwell Server Edition amendment — 2026-08-24

After the A100 allocation, `US-MD-1` volume, and H100 NVL paths all stopped
before compute, the operator approved exactly one Secure Cloud `NVIDIA RTX PRO
4500 Blackwell Server Edition` feasibility attempt in `US-KS-2`. This amendment
does not authorize a fallback GPU, a repeated create request, the 20-episode
evaluation, or production live sessions.

| Check | Result |
| --- | --- |
| RunPod account | PASS: authenticated balance `$22.0474149943`, current spend `$0.002/hour` from the existing volume, spend limit `$80`. |
| Existing Pods and daily Pod usage | PASS: zero active Pods; authenticated Pod billing contains no 2026-08-24 compute charge. |
| Exact GPU and location | PASS at check time: exact ID `NVIDIA RTX PRO 4500 Blackwell Server Edition`, 32 GB, Secure Cloud, `US-KS-2` stock `Low`, `$0.72/hour`. |
| Conservative reservation | PASS: 20 minutes reserves `$0.24`, below the issue's `$5` UTC-day allowance and available account balance. |
| Network volume | PASS: `68s0bxbv7p`, 20 GB, `US-KS-2`; enough for the 7,473,096,344-byte model and evidence. |
| Staged checkpoint metadata | PASS: exact `REVISION` plus all five required config/processor objects; no model weight is present before same-Pod bootstrap. |
| Hub identity and snapshot access | PASS: authenticated as the project account; exact revision resolves; all six required files are present; a ranged authenticated model request returned HTTP 206. The model card reports the `gemma` license and is not gated. |
| Immutable GPU image | PASS: Artifact Registry resolves `us-central1-docker.pkg.dev/robium-prod/robium/vla-pick-and-place@sha256:49c2a30a8fd7c88c3db0c21a18d4df785bf692affde06f2d9527b4e25ae28595`. |
| Template and registry | PASS: user template `e56b2xl1y1` points at the immutable image, `/models`, port `8765/http`, and the exact bootstrap command; registry credential `cmt6r3i1c004cq5uqoj4666yr` exists and will be supplied explicitly at create. |
| CUDA compatibility control | PASS before allocation: the locked image contains PyTorch 2.10 CUDA 12.8 libraries. Create will require minimum CUDA 12.8; the container will verify device, driver, runtime, compute support, and a CUDA tensor operation before checkpoint download. |
| Access and deletion path | PASS: a matching local private SSH key is loaded and registered; official `runpodctl` get/logs/SSH/delete commands are available. Create will set a provider-enforced absolute termination timestamp 20 minutes ahead and deletion will also run in `finally`. |

No Pod or other resource was created during this preflight. Exact stock, balance,
zero-Pod state, and the termination timestamp must be refreshed immediately
before the single create request.
