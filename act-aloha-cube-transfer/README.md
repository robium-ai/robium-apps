# ACT ALOHA Cube Transfer

Run a published Action Chunking with Transformers policy on the simulated
ALOHA bimanual cube-transfer task. Switch between manual joint control and the
pretrained policy, randomize the layout, and inspect the camera and live status
in one browser.

No training, NVIDIA server, or physical ALOHA robot is required.

**Stack:** LeRobot 0.6.1, the official ACT 80k checkpoint, gym-aloha, MuJoCo,
Gradio 6, uv, Python 3.12, native Apple MPS, and an optional CPU image.

## What you can do

- Run the pinned official `lerobot/act_aloha_sim_transfer_cube_human` model.
- Randomize the simulated cube layout from either control mode.
- Execute the complete 100-action horizon from each policy prediction.
- Manually pose all 14 named joints with compact left/right arm switching.
- Watch the transfer directly in a focused MuJoCo camera view.

The official LeRobot evaluation reports **83% success over 500 episodes**.
Our five-seed Apple MPS calibration produced two successes, and seed 1001
replayed successfully in 236 steps. Five local episodes are useful runtime
evidence, not a replacement estimate for the published benchmark.

## Quick start

The native path is the default on macOS because it can use Apple Metal
acceleration. Install [uv](https://docs.astral.sh/uv/), then run:

```bash
cd act-aloha-cube-transfer
./app doctor
./app run
```

Open [http://localhost:8765](http://localhost:8765).

`./app run` prepares the environment and pinned checkpoint automatically when
needed. The first build downloads about 207 MB of model source plus Python
dependencies; later starts reuse both.

Press Ctrl-C in the foreground terminal, or use `./app stop` from another
terminal.

## Use the policy workspace

### Switch control modes

ACT observes the top camera and fourteen joint values, then predicts 100
fourteen-dimensional actions in one forward pass. Select **Manual control** to
drive one arm at a time, or **Pretrained ACT model** to run the official model
with its complete 100/100 action horizon. Only the active mode is shown.

### Randomize layouts

Seed 1001 is the default because it completed a transfer twice during local
calibration. Randomize is always available and creates a new deterministic
cube placement for either control mode.

### Watch the simulator

The simulator exposes five task stages: reaching, right-gripper contact, cube
lifted, left-gripper contact, and transfer complete. The MuJoCo camera is the
only visualization in the main panel; current progress and inference time stay
in the compact Health field on the left.

The independently scrolling left panel shows one arm's manual controls at a
time, so the camera stays visible while scrolling through the sliders.
The six arm targets use radians and follow the model's real joint limits;
gripper values run from 0 (closed) to 1 (open). Manual mode starts live control
automatically, advances physics at 50 Hz, and streams the top camera at 30 FPS.
The command and frame queues retain only their newest item, so rapid movement
drops stale work instead of building latency. Starting a policy rollout stops
the manual simulator first.

## Commands

The repository-local launcher matches the other Robium reference apps.

| Command | Purpose |
| --- | --- |
| `./app doctor` | Check uv, lockfile, checkpoint, port 8765, MPS, and optional Docker |
| `./app build` | Prepare the exact environment and official migrated checkpoint |
| `./app run` | Build if needed, then run the native workspace |
| `./app status` | Show process, device, URL, PID, and log path |
| `./app logs` | Follow the current or latest workspace log |
| `./app stop` | Stop the native workspace |

`./app build` is optional for normal use because `./app run` invokes it when
required.

## Native and container paths

Native uv is the best local path on Apple Silicon. Docker Desktop cannot pass
the Mac's MPS accelerator into a Linux container.

The CPU image exists for reproducible headless and website sessions:

```bash
make demo-image
make demo-container
```

The image bakes the migrated checkpoint and local evidence, runs MuJoCo with
EGL, and disables Hugging Face network access at runtime.

## Checkpoint compatibility

The model is pinned to revision
`ba73b2766f1371cdc133ca4efb97eb090d744625`. Its source weights remain
untouched in a revisioned directory.

The checkpoint predates LeRobot's standalone policy processor files. During
`./app build`, the app runs LeRobot's official normalization migration, checks
that all remaining model tensors match, hashes the source and migrated
artifacts, and writes a provenance manifest. It never substitutes another
dataset's statistics or silently downloads a floating revision.

## How it works

```text
Pinned official checkpoint + upstream processor migration
                            |
                            v
          ACT predicts a 100 x 14 action chunk
                            |
                            v
        seeded ALOHA Transfer Cube environment
                            |
                            v
             focused MuJoCo camera view
```

MuJoCo's macOS windowing backend must be created on the main thread. Gradio
callbacks run on workers, so preview and rollout environments live in spawned
child processes. This also gives Stop a clean cooperative cancellation
boundary and prevents concurrent episodes from sharing simulator state.

See [the architecture brief](docs/architecture-brief.md) for the complete
design and measured risks, and [the tutorial](docs/case-study.md) for the
policy-selection and implementation walkthrough.

## Testing

| Command | Purpose |
| --- | --- |
| `make smoke` | Check launcher behavior, deterministic simulation, migration, real inference, and a real rollout |
| `make demo-smoke` | Check complete inline simulator frames |
| `make demo-container-smoke` | Boot the CPU gateway, verify session guards/UI, and complete seed 1001 through the API |
| `make calibrate` | Re-run the bounded five-seed local evidence set |

## Troubleshooting

- Run `./app doctor` before the first run or after changing Python or Docker.
- If port 8765 is busy, use `PORT=8766 ./app run`.
- Use `./app logs` to inspect model loading, device choice, and Gradio startup.
- The first live rollout may pause briefly while ACT and Metal warm up.
- If MPS is unavailable, the app reports and uses CPU rather than pretending
  Metal acceleration is active.

## Hosting

The gateway exposes the same private start/status/stop contract as the PushT
reference app. Website integration and production deployment are managed in
the separate `robium-website` repository; building this app does not deploy
anything.
