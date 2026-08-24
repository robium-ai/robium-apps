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

- [RunPod Pod create API](https://docs.runpod.io/api-reference/pods/POST/pods)
- [RunPod Pod list API](https://docs.runpod.io/api-reference/pods/GET/pods)
