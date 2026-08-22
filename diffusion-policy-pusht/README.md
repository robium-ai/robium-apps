# PushT with Diffusion Policy

An evidence-first imitation-learning demo built around LeRobot's published
PushT Diffusion Policy. It runs natively on Apple Silicon: no local training
or NVIDIA server is required.

**Stack:** LeRobot 0.6.0 · Diffusion Policy · gym-pusht · Gradio 6 · Rerun · uv · Python 3.12

## What the demo shows

- The pinned official `lerobot/diffusion_pusht` 175k checkpoint, with its
  published 500-episode evidence: **65.4% success** and **0.955 average maximum
  overlap** using the 100-step inference schedule.
- Live 300-step rollouts on macOS MPS, with a fast 10-denoise mode for
  interaction and a 100-denoise reference mode.
- A direct 96×96 policy view plus an additive, scrub-able Rerun action and
  coverage timeline.
- Exact and randomized layout seeds. Keep a seed fixed while changing policy
  or inference mode, then replay it.
- T as the benchmark and explicitly qualitative L/I/Z
  out-of-distribution probes. Those letters were not in the training data.

PushT success uses the environment's real threshold: at least 95% target
coverage. The published policy's 65.4% result is below this app's aspirational
70% release bar, so the app remains experimental rather than inflating the
claim.

## Run on macOS

Apple Silicon is the primary local path. Docker is intentionally not used
because macOS containers cannot access MPS.

```bash
brew install ffmpeg
make sync
make prepare-official
make smoke
make demo
```

Open [http://localhost:8765](http://localhost:8765). The first preparation
downloads roughly 1 GB; later runs use the local cache. `make smoke` performs
no training: it validates provenance and completes a real official-policy
episode. On the Apple M5 used for this build, fast mode completed a full
300-step seed-12000 rollout in about 21 seconds and reached 0.920 maximum raw
coverage. One seed is a runtime check, not a replacement benchmark.

## Fast versus reference inference

Diffusion Policy starts each planned action sequence as noise and repeatedly
denoises it. The setting controls how many cleanup passes happen before the
robot executes the sequence:

| Mode | Denoising passes | Use |
| --- | ---: | --- |
| Fast | 10 | Responsive local exploration; no published success claim |
| Reference | 100 | Matches the official checkpoint's published evaluation schedule; slower on MPS |

Changing denoising passes does not retrain or modify the checkpoint. The
published 65.4% success number applies to the official 100-pass evaluation,
not to fast mode.

## Evidence and compatibility

The model is pinned to Hugging Face revision
`84a7c23178445c6bbf7e1a884ff497017910f653`. Its original weights are
unchanged. Because this older checkpoint predates LeRobot 0.6's standalone
policy processors, `make prepare-official` deterministically creates those
processor files from the canonical `lerobot/pusht` dataset statistics and
writes `robium-provenance.json`.

If the local 5k experiment is present, the page shows it as separate,
incomplete evidence: 1/30 successes and 0.376 average maximum raw coverage
before its 50-seed run was stopped. It is **not** presented as an earlier
point in the official model's learning curve because its training
configuration differs. The official repository does not publish intermediate
checkpoints.

The checkpoint is published under Apache-2.0; this application's source is
MIT. See the [official model card](https://huggingface.co/lerobot/diffusion_pusht).

## Commands

| Command | Contract |
| --- | --- |
| `make check` | Validate uv, ffmpeg, lockfile, environment, and manifest. |
| `make prepare-official` | Fetch the pinned checkpoint, create LeRobot 0.6 processors, and generate the evidence manifest. |
| `make smoke` | Validate provenance and complete one full fast-mode official-policy rollout. |
| `make demo` | Prepare if needed and start the local Gradio + Rerun app with native MPS inference. |
| `make demo-smoke` | Boot the real app and complete T and OOD rollouts through its public API. |

The older `train-*`, `calibrate`, and `eval-ladder` targets remain only
for reproducing the separate local research experiment. They are not part of
setup or the app pass bar.

## Design notes

- `outputs/demo/ladder.json` is generated from official and local evidence;
  the UI contains no hand-entered performance numbers.
- Runs are serialized. Stop is cooperative and takes effect at the next
  simulator step.
- The primary rollout is visible without Rerun; Rerun provides deeper
  inspection.
- ACT is better reserved for a separate, faster pick-and-place demonstration.

The approved redesign and official-checkpoint pivot are recorded in
`docs/superpowers/specs/2026-08-21-diffusion-policy-pusht-redesign.md`.
