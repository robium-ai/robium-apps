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

## Noninteractive LIBERO configuration — 2026-08-24

The diagnostics-enabled paid retry persisted `EOFError: EOF when reading a
line` at `model_loading`. Source inspection at the pinned LIBERO revision
confirmed that first import prompts for a dataset path when its config file is
absent. The remediation bakes the config rather than relying on a writable home
directory or container stdin.

| Gate | Result |
| --- | --- |
| Red/green container contract | PASS: the test first failed because the GPU runtime did not copy a LIBERO config, then passed after the image contract was added |
| Full local regression | PASS: doctor, 27 tests, deterministic five-frame fake smoke |
| Linux/amd64 GPU image | PASS: locally built image ID `sha256:4eae0bd35d85aec4e33b39cb304baf51ca351b26e4bd3a2b688a276cbc75c677` |
| Closed-stdin LIBERO import | PASS: the exact GPU image printed `LIBERO NONINTERACTIVE CONFIG PASS` without a prompt |
| Pinned paths | PASS: assets, BDDL files, benchmark root, and initial states exist in `/opt/libero`; the dataset path is fixed at `/opt/libero/libero/datasets` |

No image was published and no Cloud Build or RunPod allocation was used for
this remediation. Paid revalidation remains a separate approval gate.

## Interactive-runtime remediation — 2026-08-24

| Gate | Result |
| --- | --- |
| Full local regression | PASS: doctor, 33 tests, deterministic five-frame fake smoke |
| Static quality | PASS: Ruff check, Ruff format check, and `git diff --check` |
| Linux/amd64 GPU packaging | PASS: local manifest `sha256:5c305881e352bcbf48ecea256e425f5c2fe42bbb1b104fdbdb8726de467b7104` validates asset hydration and exact task reset; the later same-path staging guard is unit-tested and was not re-exported |
| Locked wheel identity | PASS with closed stdin: `libero.libero` resolved under `/app/.venv/lib/python3.10/site-packages` rather than the older source checkout |
| Hydrated module-relative asset | PASS: `libero_tabletop_base_style.xml` exists beside the imported wheel module |
| Exact environment reset | PASS under EGL: task 8 resolved to `put_the_bowl_on_the_plate` and returned a 256×256 frame |
| Two-snapshot bootstrap | PASS in free tests: exact checkpoint and tokenizer revisions/files are required, revision markers are written last, and Hub credentials are removed from offline children |
| Local checkpoint staging | PASS in free tests: stale staging content is replaced, the staged snapshot is validated, and the offline child receives the staged path |
| Tied-weight guard | PASS in free tests: shared storage is accepted and untied embedding/head storage fails closed |

The gated tokenizer file download is not a free PASS: the configured Hugging
Face account returned HTTP 403. No image was published and no further cloud
compute was used after that licensing gate failed.

## Publication and interactive-latency remediation — 2026-08-24

| Gate | Result |
| --- | --- |
| Publication self-reference | PASS: the manifest no longer requires its own future commit hash; a separately schema-validated pointer pins the final 40-character dataset revision and manifest SHA-256 |
| Publication command order | PASS: `evaluate` records 20 immutable-input episodes, `finalize-publication` validates hashes and measured cost, and `record-publication` runs only after the Hub revision exists |
| Immutable evaluation startup | PASS: exact app commit, image digest, and RTX PRO 4500 identity are validated before CUDA; the compiled evaluator receives an offline, token-free environment; artifacts and `evaluation_complete` persist on the network volume; only the lightweight parent waits for controller deletion |
| No-retry restart guard | PASS: diagnostics may precede evaluation, but any existing episode video/record, evaluation-run metadata, or manifest makes the evaluator refuse to retry or overwrite measured output |
| Runtime profiles | PASS: feasibility and paid evaluation select compiled execution; the real gateway defaults to explicit eager execution |
| First visible update | PASS: the rollout generator emits `starting` before waiting for the first simulator frame and keeps the run control noninteractive while active |
| Duplicate rollout | PASS: a concurrent request returns a readable `busy` state and does not expose `RolloutBusyError` to the visitor |
| Full local regression | PASS: doctor, 46 tests, deterministic five-frame fake smoke, Python compileall, Ruff check/format, and `git diff --check` |
| Linux/amd64 CPU image | PASS: rebuilt immutable local manifest `sha256:c4987ec8a88055822260e9530763c39f5d831db13fac6c98328489067e9643ca` |
| Linux/amd64 GPU image | PASS: full pinned CUDA/LeRobot/LIBERO/evaluation-startup target rebuilt locally as manifest `sha256:4ca784599854e2c95d5241bdf65cbda03064724aa09236a410f670fa304b57a4` |
| Rebuild cache contract | PASS: dependency sync uses BuildKit uv cache mounts and README/source layers follow the locked dependency layer, so content-only changes do not invalidate the multi-gigabyte environment |
| Protected container lifecycle | PASS: unscoped and foreign routes returned 404; the protected UI loaded; one rollout returned simulator success and nonblank frames; shutdown returned before the container exited |

No Cloud Build, registry publication, RunPod allocation, Hugging Face upload,
or other paid compute was used for this remediation. The 20-episode evaluation
remains a separate paid-compute and public-publication approval gate.
