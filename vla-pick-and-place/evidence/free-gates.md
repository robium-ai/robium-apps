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
