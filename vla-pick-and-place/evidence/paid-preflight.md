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
