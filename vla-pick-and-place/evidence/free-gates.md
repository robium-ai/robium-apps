# Free gate evidence

Verified 2026-08-23 before any credential, billing, checkpoint-load, or Pod
operation.

| Gate | Command | Result |
| --- | --- | --- |
| Local doctor | `./app doctor` | PASS on pinned CPython 3.10.20 |
| Unit/integration | `uv run pytest` | 14 passed |
| Local fake rollout | `./app smoke` | PASS; 5 nonblank frames; simulator fixture success |
| Clean environment | isolated `UV_PROJECT_ENVIRONMENT` sync, test, doctor, smoke | PASS; 14 tests |
| Linux/amd64 CPU image | `./app image-fake` | PASS; `sha256:43c6d3ba714eb2b70930e41cfdcd52ca0796b3247b44c182a9ed36e6f93c9306` |
| Protected container routes | root, missing capability, foreign capability | 404, 404, 404 |
| Container claim/UI/rollout | correct capability plus Gradio `/run_rollout` | claim 200; UI 200; 5 nonblank frames; success true |
| Container shutdown | capability-scoped shutdown then inspect | response received; container absent |

The first image build caught and fixed an invalid uv invocation: in uv 0.11.29,
`--no-extra` requires an extra name; omitting all `--extra` flags is the correct
base-only sync.

## RTX PRO 4500 amendment rerun — 2026-08-24

All free gates were rerun after the approved feasibility-hardware amendment and
before its paid preflight.

| Gate | Result |
| --- | --- |
| Local doctor | PASS on pinned CPython 3.10.20 |
| Unit/integration | 17 passed |
| Local fake rollout | PASS; 5 nonblank frames; simulator fixture success |
| Linux/amd64 CPU image | PASS; `sha256:d504367b60f7350b680eaf25c8e1ae74788f96214db1197c6c1df38b4764b2e8` |
| Protected container routes | root 404; missing capability 404; foreign capability 404 |
| Container claim/UI/rollout | claim 200; UI 200; 5 nonblank frames; success true |
| Container shutdown | response received; process stopped; cleanup left no test container |

## Numeric-runtime-user remediation — 2026-08-24

The allocated GPU container exposed that `USER 65532:65532` had no passwd
entry, causing PyTorch Inductor's `getpass.getuser()` call to fail before CUDA.

| Gate | Result |
| --- | --- |
| Reproduction against old CPU image | PASS: `getent passwd 65532` exited 2 |
| Rebuilt CPU image identity | PASS: UID/GID 65532 resolves to `robium`, home `/tmp`, nologin shell |
| Python identity | PASS: `os.getuid() == 65532`, `getpass.getuser() == "robium"`, `HOME == "/tmp"` |
| Pinned CUDA runtime base | PASS: the same group/user creation and lookup succeed on the exact CUDA runtime digest |
| Local regression | PASS: doctor, 17 tests, fake smoke with 5 nonblank frames |
| Protected container regression | PASS: genuine fake rollout result, 5 frames, shutdown response, process stopped |

The corrected local CPU image digest is
`sha256:ab149bf81d6c4dc938283677f8b50f4cb5fa1e188a2ee5d8639fed95631485e2`.
No corrected GPU image was published as part of this free remediation.

## Baked compatibility-first startup — 2026-08-24

| Gate | Result |
| --- | --- |
| Request-time override removed | PASS: GPU image entrypoint is the committed `vla_pick_and_place.startup` module; template entrypoint and start-command overrides are unset |
| Ordering | PASS: CUDA/device/tensor preflight runs before checkpoint validation or download |
| Existing snapshot | PASS: complete revision skips download and launches with Hub/Transformers offline and `HF_TOKEN` removed |
| Missing snapshot | PASS: exact bootstrap runs, then the child environment is token-free and offline |
| Feasibility lifecycle | PASS: one measured CLI run is followed by the offline gateway on the same process/Pod lifecycle |
| Full local regression | PASS: doctor, 20 tests, deterministic five-frame fake smoke |
| Final immutable GPU build | PASS: Cloud Build `6b7bee99-33da-4fc7-96f2-eced08115344`, digest `sha256:65eb29edb290952ae46c1244fe77edb5dade83546f75389eb3083866c56cf690` |

## Persistent startup diagnostics — 2026-08-24

This free remediation followed the paid retry whose durable checkpoint evidence
proved startup while RunPod reported `runtime: null`, but whose post-bootstrap
exception was otherwise unavailable.

| Gate | Result |
| --- | --- |
| Atomic phase markers | PASS: the marker names the active stage and leaves no temporary file after replacement |
| Sanitized failure markers | PASS: configured secrets, Hugging Face token shapes, traceback, and environment contents are absent; stage, exception class, bounded message, return code, and UTC timestamp remain |
| Exact model-load stage | PASS: a simulated runner-construction failure persisted `model_loading` rather than only the outer subprocess stage |
| Startup ordering | PASS: durable stages cover CUDA preflight, checkpoint validation/bootstrap, model loading, rollout, artifact write, and gateway handoff |
| Full local regression | PASS: doctor, 26 tests, deterministic five-frame fake smoke |
| Linux/amd64 CPU image | PASS: `sha256:e1fdb18e544cd55a3846faf72f9ca66c99d23ad50634246d3616f7dceaadd726` |
| Protected container lifecycle | PASS: hidden unscoped routes, capability claim, five-frame successful rollout, shutdown response, and confirmed container removal |

No Cloud Build, registry publication, RunPod allocation, checkpoint load, or
other paid compute was used for this diagnostics gate.
