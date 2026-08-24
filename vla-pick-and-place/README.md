# Pi0.5 VLA pick and place

This app evaluates the official
[`lerobot/pi05_libero_finetuned_v044`](https://huggingface.co/lerobot/pi05_libero_finetuned_v044)
checkpoint on one fixed benchmark: the Franka Panda in zero-based
LIBERO-Goal task 8, `put_the_bowl_on_the_plate`.

The canonical instruction is **“put the bowl on the plate.”** Edited prompts
are allowed in the eventual live workspace but are labeled experimental. Each
run is a complete autonomous rollout: there is no pause, manual stepping,
scene editing, or multi-task selector. Frames come from the simulator and the
result comes only from LIBERO's sparse success signal.

The public 20-episode evaluation is not claimed. A corrected RTX PRO 4500 retry
on 2026-08-24 passed CUDA 12.8/Blackwell compatibility and populated the exact
7.473 GB checkpoint on the private volume. A diagnostics-enabled retry then
identified the post-bootstrap failure exactly: pinned LIBERO prompted for a
dataset path during its first import, and closed container stdin raised
`EOFError` at `model_loading`. The GPU image now bakes a deterministic LIBERO
config, and a local Linux/amd64 GPU-image import passes with closed stdin. A
paid revalidation confirmed that fix, then exposed a second exact packaging
defect: Python imported dependency-installed `hf-libero` from `site-packages`,
whose wheel lacks the required scene assets, instead of the pinned checkout at
`/opt/libero`. The Pod was deleted before an episode. Making the pinned
checkout the authoritative import source and repeating the paid gate remain
pending. All later paid and deployment gates remain blocked. Production live
sessions remain disabled pending separate operator approval.

## What is pinned

| Component | Immutable revision |
| --- | --- |
| Pi0.5 checkpoint | `8e174154ef5f6c60a8da12ae99c303d8963138c1` |
| LeRobot v0.4.4 | `8fff0fde7c79f23a93d845d1a50e985de01f8b8a` |
| LIBERO | `8f1084e3132a39270c3a13ebe37270a43ece2a01` |

The runtime uses Python 3.10, `n_action_steps=10`, batch size 1, at most 300
steps, and `MUJOCO_GL=egl` in the Linux CUDA image. The checkpoint is loaded
offline from a private network volume and is not baked into the image. The
image sets `LIBERO_CONFIG_PATH=/app/libero-config` and bakes paths for the exact
LIBERO checkout under `/opt/libero`, so startup never prompts for local input.

## Free local workflow

Local macOS does not load Pi0.5. It exercises the same prompt, state mapping,
rollout lock, cancellation, evidence validation, gateway, and Gradio UI with a
deterministic fake policy and three compact official task-8 frames.

```bash
./app doctor
./app test
./app smoke
./app run
```

The local UI uses this development-only capability URL:

```text
http://127.0.0.1:8765/c/local_0123456789abcdefghijklmnopqrstuvwxyz/ui/
```

Build the pinned Linux/amd64 CPU target before any paid gate:

```bash
./app image-fake
```

The GPU image target is also reproducible locally, but building or publishing
it does not authorize a RunPod allocation:

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

`evidence/manifest.schema.json` defines the committed evidence contract. The
eventual public Hugging Face dataset contains every MP4 and per-episode record;
Git contains only the validated manifest, summary, schema, and three previews.

## Architecture and upstream guidance

- [Active architecture brief](docs/architecture-brief.md)
- [Approved redesign specification](docs/superpowers/specs/2026-08-23-pi05-libero-runpod-redesign.md)
- [Ordered implementation gates](docs/superpowers/plans/2026-08-23-pi05-libero-runpod-implementation.md)
- [Official LeRobot Pi0.5 documentation](https://huggingface.co/docs/lerobot/pi05)

This app intentionally has no training wrapper. Use upstream LeRobot guidance
for training and fine-tuning.
