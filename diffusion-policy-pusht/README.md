# PushT with Diffusion Policy

Run a published visual Diffusion Policy on a laptop and inspect how it pushes
a T-shaped block into a target. The app uses LeRobot's official PushT
checkpoint, provides repeatable seeded layouts, and compares responsive and
reference-quality inference in one browser workspace.

No training, NVIDIA server, or physical robot is required.

**Stack:** LeRobot 0.6.0, Diffusion Policy, gym-pusht, Gradio 6, Rerun, uv,
Python 3.12, and an optional CPU Docker image.

## What you can do

- Run the pinned official `lerobot/diffusion_pusht` 175k checkpoint.
- Replay the same T layout by keeping its seed fixed.
- Generate new layouts with a random seed.
- Compare 10-step interactive inference with the checkpoint's 100-step
  reference schedule.
- Inspect the live 96×96 observation, action sequence, and target coverage.
- Try L, I, and Z blocks as qualitative out-of-distribution probes.
- Compare the official policy with the separate, incomplete local 5k
  experiment without presenting them as one learning curve.

PushT counts an episode as successful when the block covers more than 95% of
the target. The official model card reports **65.4% success** and **0.955
average maximum normalized reward** over 500 episodes with the 100-step
inference schedule.

## Quick start

The native path is the default on macOS because it can use Apple Metal
acceleration. Install [uv](https://docs.astral.sh/uv/) and ffmpeg, then run:

```bash
cd diffusion-policy-pusht
./app doctor
./app run
```

Open [http://localhost:8765](http://localhost:8765).

`./app run` prepares the uv environment and pinned checkpoint automatically
when either is missing. The first run downloads roughly 1 GB. Later runs reuse
the local environment and checkpoint cache.

Press Ctrl-C in the foreground terminal to stop the app, or use `./app stop`
from another terminal.

## Use the policy workspace

### Choose policy evidence

**Official LeRobot 175k** is the default and the only option with a published
500-episode result. Its revision is pinned, and the application records the
compatibility conversion used to load it in LeRobot 0.6.

**Local 5k experiment** is retained as separate evidence. Its evaluation was
stopped after 30 of 50 seeds, with one success. It is not an earlier point in
the official model's training curve because the configurations differ.

### Choose inference quality

Diffusion Policy begins with a noisy action sequence and repeatedly refines it
before executing a short portion of that sequence.

| Mode | Denoising steps | Use |
| --- | ---: | --- |
| Fast | 10 | Responsive local exploration; no published success claim |
| Reference | 100 | The official checkpoint's published evaluation schedule |

The checkpoint does not change when you switch modes. Only the number of
denoising iterations used to produce each action sequence changes.

### Replay and randomize layouts

Enter an exact seed to reproduce a layout. Keep the seed fixed while changing
policy evidence or inference quality so the visual comparison remains useful.
Use the randomize control to generate another layout.

The published evaluation used T layouts seeded from 1000 through 1499. Layouts
outside that range remain useful experiments, but the app labels them
qualitative rather than attaching the published success rate.

### Probe other block shapes

T is the benchmark geometry and runs in the untouched upstream
`gym_pusht/PushT-v0` environment. L, I, and Z use a generalized local
environment. The policy was not trained on those shapes, so they are
out-of-distribution probes rather than benchmark results.

## Commands

Run `./app help` for the current command list. The repository-local launcher
matches the command surface used by the Robot Navigation reference app.

| Command | Purpose |
| --- | --- |
| `./app doctor` | Check uv, ffmpeg, the lockfile, checkpoint readiness, port 8765, and optional Docker availability |
| `./app build` | Prepare the uv environment and pinned official checkpoint explicitly |
| `./app run` | Build if needed, then run the native policy workspace |
| `./app status` | Show whether the workspace is running, plus its PID, URL, and log path |
| `./app logs` | Follow the current or most recent application log |
| `./app stop` | Stop the running policy workspace |

`./app build` is optional for normal use because `./app run` invokes it
when required.

## Native and container paths

The native uv path is intended for local use. On Apple Silicon it uses MPS,
which is substantially faster than running the same policy inside Docker.
Docker Desktop cannot pass the Mac's Metal accelerator into a Linux container.

The CPU image exists for the website demo and reproducible headless sessions:

```bash
make demo-image
make demo-container
```

The image contains the pinned checkpoint and runs with Hugging Face network
access disabled. It is slower than native MPS but matches the hosted runtime.
These are maintainer and deployment-parity commands, not prerequisites for
`./app run`.

## Evidence and checkpoint compatibility

The model is pinned to Hugging Face revision
`84a7c23178445c6bbf7e1a884ff497017910f653`. Its weights remain unchanged.

The checkpoint predates LeRobot 0.6's standalone policy processor files.
During `./app build`, the application creates current processor files from
the normalization buffers embedded in the original model and writes
`robium-provenance.json`. Exact tensor checks protect that conversion.

This detail matters. Regenerating processors from the current dataset's pixel
statistics produced visibly worse behavior because the legacy model used
ImageNet image normalization.

The official repository does not publish intermediate checkpoints, so the
application does not invent a checkpoint ladder. It shows attributed
published evidence beside live, seeded rollouts.

## How it works

```text
Pinned LeRobot checkpoint + processor conversion
                       |
                       v
        visual Diffusion Policy on MPS or CPU
                       |
                       v
          seeded PushT environment and metrics
                       |
                       v
        Gradio workspace + additive Rerun timeline
```

The direct RGB policy frame is the primary view. Rerun adds a scrub-able
timeline for observations, actions, and coverage without becoming a
requirement for seeing the rollout.

Runs are serialized so two episodes cannot mutate one environment at the same
time. Stop is cooperative and takes effect at the next simulator step.

See [docs/architecture-brief.md](docs/architecture-brief.md) for the complete
architecture and [docs/case-study.md](docs/case-study.md) for the tutorial and
policy-selection discussion.

## Testing and research commands

The public launcher stays focused on operating the app. Maintainer checks and
the earlier training experiment remain in the Makefile:

| Command | Purpose |
| --- | --- |
| `make smoke` | Validate provenance and complete one official fast-mode rollout |
| `make demo-smoke` | Start the real gateway and complete T and OOD rollouts through its API |
| `make demo-container-smoke` | Verify the CPU image, session guards, UI, and one real T rollout |
| `make train-smoke` | Exercise a short train-to-checkpoint pipeline |
| `make train-to-5k` | Reproduce the first gate of the separate local experiment |

Training is not part of application setup.

## Troubleshooting

- Run `./app doctor` before the first run or after changing Python, ffmpeg,
  Docker, or port settings.
- Run `./app status` to confirm the process and URL.
- Run `./app logs` to inspect checkpoint loading, device selection, and
  Gradio startup.
- If port 8765 is busy, stop its owner or choose another port:
  `PORT=8766 ./app run`.
- macOS may print warnings about duplicate SDL or AVFoundation classes from
  OpenCV, Pygame, and PyAV. The verified seeded rollouts remain stable despite
  those warnings.
- If an interrupted run leaves stale state, `./app stop` clears a live
  process; a stale PID is removed automatically by `status`, `doctor`, or
  the next run.

## Live demo

The website presents two choices: start a private temporary CPU instance or
run the native application locally. The hosted path uses the same policy,
evidence manifest, seeded environment, and Gradio workspace.

Try it at
[robium.ai/demos/diffusion-policy-pusht](https://robium.ai/demos/diffusion-policy-pusht/).

Image publication and production deployment are maintained separately from
the local application workflow.
