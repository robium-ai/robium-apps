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

The immutable public evaluation passed **20/20 episodes** (states 0–19, seeds
1000–1019, no retries) on an RTX PRO 4500 on 2026-08-25, exceeding the 16/20
acceptance target. The first episode took 239.239 seconds because its first
compiled action took 231.214 seconds; the remaining 19 episodes averaged 6.357
seconds. The complete public evidence is pinned at [Hugging Face revision
`d9908eb717d3e8d62ca7ba0820a825daf36fa7c0`](https://huggingface.co/datasets/robium/pi05-libero-goal-task-8-evidence/tree/d9908eb717d3e8d62ca7ba0820a825daf36fa7c0),
with the checked-in summary and previews in [evidence/results.md](evidence/results.md).
The private RunPod template remains safely pinned with `VLA_LIVE_ENABLED=false`;
the production controller explicitly enables allocation after the operator's
2026-08-26 approval. The final public production smoke passed with immutable
image digest `sha256:4613c522…606a`: capability isolation, a genuine state-0
rollout, active cancellation, and confirmed Pod deletion all passed. See
[evidence/live-integration-smoke.md](evidence/live-integration-smoke.md).

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

## Architecture and upstream guidance

- [Active architecture brief](docs/architecture-brief.md)
- [Approved redesign specification](docs/superpowers/specs/2026-08-23-pi05-libero-runpod-redesign.md)
- [Ordered implementation gates](docs/superpowers/plans/2026-08-23-pi05-libero-runpod-implementation.md)
- [Official LeRobot Pi0.5 documentation](https://huggingface.co/docs/lerobot/pi05)

This app intentionally has no training wrapper. Use upstream LeRobot guidance
for training and fine-tuning.
