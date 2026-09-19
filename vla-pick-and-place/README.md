# Pi0.5 VLA pick and place

Give the official
[`lerobot/pi05_libero_finetuned_v044`](https://huggingface.co/lerobot/pi05_libero_finetuned_v044)
model one instruction — **“put the bowl on the plate”** — and watch a simulated
Franka Panda work out the movements. Change the words, replay three starting
scenes, or watch all 20 saved attempts.

The local application uses deterministic fixtures and does not require an
NVIDIA GPU. Real Pi0.5 inference runs in the pinned Linux CUDA image.

**Stack:** LeRobot 0.4.4, the official Pi0.5 LIBERO checkpoint, LIBERO, MuJoCo,
Gradio, uv, Python 3.10, local fixtures, and a RunPod NVIDIA GPU runtime.

## What you can do

- Choose one of three fixed LIBERO initial states with the canonical instruction.
- Edit the instruction for clearly labeled qualitative experiments.
- Watch the complete autonomous task and its plain-language status.
- Watch all 20 attempts and download the files used to make them.
- Exercise prompt, state, cancellation, evidence, and private-session behavior
  locally without allocating a GPU.

We tried 20 different starting arrangements on an RTX PRO 4500. The robot put
the bowl on the plate in all 20. Each attempt started fresh and was counted
once; this tells you what happened in those saved runs, not what every robot
will do in every scene.

## Quick start

Install [uv](https://docs.astral.sh/uv/), then run:

```bash
cd vla-pick-and-place
./app doctor
./app run
```

Open the capability URL printed by the launcher. The local workspace uses a
deterministic fake policy with three compact official task-8 frames. It
exercises the same prompt rules, state mapping, rollout lock, cancellation,
evidence validation, gateway, and Gradio UI as the hosted path.

| Command | Purpose |
| --- | --- |
| `./app doctor` | Check the environment and application contract |
| `./app test` | Run the focused unit and contract tests |
| `./app smoke` | Exercise one complete deterministic local rollout |
| `./app run` | Start the fixture-backed workspace |

## Use the policy workspace

Choose an initial state, edit the instruction if you want, then select **Run
task**. Keeping the state fixed makes instruction experiments comparable.
Edited instructions are experimental and do not inherit the published 20/20
result.

Each run is one complete autonomous task. There is no manual stepping, scene
editing, or scripted grasp controller. Frames come from the simulator, and the
result comes only from LIBERO's sparse success signal. The compact left rail
holds the initial state, editable instruction, Run task, Stop, and status;
the rest of the workspace is reserved for the simulator image. The interface
allows one task at a time and turns a duplicate click into a readable busy
state.

## What happened

The first attempt looked frozen for almost four minutes while PyTorch prepared
the model for the GPU. After that one-time work, the remaining 19 attempts took
about six seconds each.

The complete set is saved at [this Hugging Face revision
`d9908eb717d3e8d62ca7ba0820a825daf36fa7c0`](https://huggingface.co/datasets/robium/pi05-libero-goal-task-8-evidence/tree/d9908eb717d3e8d62ca7ba0820a825daf36fa7c0).
The checked-in [result summary](evidence/results.md) explains how we ran it and
links the three previews.

The final production lifecycle smoke used immutable image digest
`sha256:4613c522…606a` and verified capability isolation, a genuine state-0
rollout, active cancellation, and confirmed Pod deletion. See the
[live integration smoke](evidence/live-integration-smoke.md).

## What is pinned

| Component | Immutable revision |
| --- | --- |
| Pi0.5 checkpoint | `8e174154ef5f6c60a8da12ae99c303d8963138c1` |
| PaliGemma tokenizer | `35e4f46485b4d07967e7e9935bc3786aad50687c` |
| LeRobot v0.4.4 | `8fff0fde7c79f23a93d845d1a50e985de01f8b8a` |
| LIBERO | `8f1084e3132a39270c3a13ebe37270a43ece2a01` |

The runtime uses Python 3.10, `n_action_steps=10`, batch size 1, at most 300
steps, and `MUJOCO_GL=egl` in the Linux CUDA image. The checkpoint and tokenizer
are verified on a private network volume, staged to transient container disk,
and loaded offline; neither is baked into the image. The image sets
`LIBERO_CONFIG_PATH=/app/libero-config`, bakes paths for the exact LIBERO
checkout under `/opt/libero`, and hydrates the locked wheel's assets, so startup
never prompts for local input or resolves module-relative files from an
incomplete wheel.

Feasibility and publication evaluation keep the checkpoint's compiled execution
path. The interactive gateway explicitly uses eager execution because the
measured first compiled action spent about 281 seconds in TorchInductor while
warm/eager actions took only a few seconds. The browser receives an immediate
starting state, the rollout button is disabled while work is active, and a
duplicate request becomes a readable busy state instead of a traceback.

## Build the runtime images

The local UI uses this development-only capability URL:

```text
http://127.0.0.1:8765/c/local_0123456789abcdefghijklmnopqrstuvwxyz/ui/
```

Build the pinned Linux/amd64 fixture target before any paid gate:

```bash
./app image-fake
```

The GPU image target is reproducible locally. Building or publishing it does
not authorize a RunPod allocation:

```bash
./app image-gpu
```

### Persistent startup diagnostics

The GPU startup writes small JSON markers to the attached `/models` volume so
a failed Pod remains diagnosable even when provider logs or runtime fields are
unavailable. `phase.json` identifies the latest stage, from CUDA preflight and
checkpoint validation through `model_loading`, `rollout`, artifact writing,
and gateway startup. `failure.json` records the stage, exception class,
sanitized bounded message, optional subprocess return code, and UTC timestamp.
Both files are replaced atomically, contain no traceback or environment dump,
and redact configured credentials and Hugging Face token shapes.

Feasibility markers live beside `cuda-preflight.json` and the eventual
`feasibility.json` under `VLA_EVIDENCE_OUTPUT`. Gateway-only startup markers use
`VLA_DIAGNOSTIC_OUTPUT`, which defaults to
`/models/issue-69-gateway-startup`. During boot, monitoring must use these
durable volume markers together with RunPod state rather than treating an
empty `runtime` field as proof that the container did not start.

## Evaluation protocol

The publication run is exactly 20 sequential episodes. State IDs 0–19 map to
seeds 1000–1019; environment and policy reset before every episode; no retries
are permitted. The target is 16/20. A lower technically valid score is
published unchanged with a prominent warning.

`evidence/manifest.schema.json` defines the evidence manifest and
`evidence/publication.schema.json` defines the immutable publication pointer.
The public Hugging Face dataset contains every MP4, per-episode record, and the
validated manifest. After upload, Git records the final 40-character
dataset revision and manifest hash in `evidence/publication.json`; the manifest
cannot contain its own content-dependent Git revision. Git otherwise keeps only
the result summary, schemas, manifest, and three previews.

The paid publication commands are intentionally split so the dataset revision
is resolved only after the complete bundle exists:

```bash
python -m vla_pick_and_place.cli evaluate \
  --output /evidence \
  --application-commit <40-character-app-commit> \
  --image-digest sha256:<64-hex-image-digest> \
  --gpu "NVIDIA RTX PRO 4500 Blackwell Server Edition"
python -m vla_pick_and_place.cli finalize-publication \
  --output /evidence --cost-usd <measured-runpod-cost>
# Upload and verify /evidence, then resolve its immutable Hub revision.
python -m vla_pick_and_place.cli record-publication \
  --manifest /evidence/manifest.json \
  --dataset-revision <40-character-hub-revision> \
  --output evidence/publication.json
```

On RunPod, the immutable entrypoint selects this evaluator with
`VLA_STARTUP_MODE=evaluation` plus `VLA_APPLICATION_COMMIT`,
`VLA_IMAGE_DIGEST`, and the exact `VLA_GPU_NAME`. It writes the candidate bundle
to `/models/issue-69-evaluation`, records `evaluation_complete`, releases the
model subprocess, and waits for controller deletion. Any pre-existing episode
artifact makes startup fail closed so a restarted Pod cannot silently retry or
overwrite a measured episode. Hugging Face credentials are not passed into the
evaluation subprocess; upload and final cost/revision resolution happen after
the Pod is deleted.

## Testing

| Command | Purpose |
| --- | --- |
| `./app test` | Run the 48 focused unit and contract tests |
| `./app smoke` | Complete a fixture-backed rollout through the local UI |
| `make image-contract-smoke` | Verify both fixture and GPU image contracts |

Paid GPU gates remain separate from local testing. The immutable publication
bundle and [live integration smoke](evidence/live-integration-smoke.md) record
the real-platform checks that cannot run on macOS.

## Hosting

The website controller allocates one capability-protected RunPod Pod per
visitor. Production admits up to three concurrent sessions, closes reservations
before provider creation, and fails closed at the $5 UTC-day budget. A ready
session lasts ten minutes; the hard expiry is twenty minutes.

Website integration and production configuration live in the separate
`robium-website` repository. Building this application does not deploy it or
authorize a paid GPU allocation.

## Architecture and upstream guidance

- [Active architecture brief](docs/architecture-brief.md)
- [Approved redesign specification](docs/superpowers/specs/2026-08-23-pi05-libero-runpod-redesign.md)
- [Ordered implementation gates](docs/superpowers/plans/2026-08-23-pi05-libero-runpod-implementation.md)
- [Official LeRobot Pi0.5 documentation](https://huggingface.co/docs/lerobot/pi05)

This app intentionally has no training wrapper. Use upstream LeRobot guidance
for training and fine-tuning.
