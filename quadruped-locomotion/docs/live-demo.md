# Live control panel — drive the trained policy in real time

An interactive demo: a web page with a live sim view + velocity **sliders,
keyboard control, and a checkpoint dropdown** that drives the trained Go2 policy
in Isaac Sim in real time. The recovered version was validated on 2026-07-27,
and the current wrapper passed a fresh capability-scoped GPU-host smoke on
2026-08-28.

![reward dashboard — clickable checkpoint videos](https://claude.ai/code/artifact/1661f6a2-c375-4975-9a90-0561517272d7)

## What it is

`scripts/live_demo_patch.py` patches Isaac Lab's compatibility
`scripts/reinforcement_learning/rsl_rl/play.py` into a `live_demo.py` that:

1. **Makes the velocity command directly controllable** — disables the task's
   random command resampling, heading-derived yaw, and standing-env zeroing, so
   the commanded `(vx, vy, yaw)` sticks to whatever the UI sends.
2. **Captures each rendered frame** (`env.render()` → downscaled JPEG).
3. **Serves an MJPEG stream + a control page + command, checkpoint, reset, and
   status endpoints** on port `8888` (the RunPod-proxied HTTP port).
4. **Hot-swaps checkpoints** — `/load` reloads a different `model_<iter>.pt` into
   the *running* runner (no reboot), so you can A/B iter-100 vs iter-1000 while
   driving.

The control page: live view, `vx`/`vy`/`yaw` sliders, preset buttons, **W/A/S/D
+ arrow keys** (Q/E strafe), and a checkpoint selector.

## Run it (on a GPU host with Isaac Lab + a trained run)

```bash
# 1. generate live_demo.py from play.py
python3 scripts/live_demo_patch.py

# 2. launch it against a checkpoint (num_envs=1, cameras on)
RUN=logs/rsl_rl/unitree_go2_flat/<timestamp>
./isaaclab.sh -p scripts/reinforcement_learning/rsl_rl/live_demo.py \
    --task Isaac-Velocity-Flat-Unitree-Go2-v0 --num_envs 1 \
    --checkpoint $RUN/model_1000.pt --enable_cameras --device cuda

# 3. open the proxied URL (RunPod:  https://<podId>-8888.proxy.runpod.net/ )
```

Set `DEMO_CAPABILITY` for a hosted session. The controller then serves only
under `/c/<capability>/`, matching the website's private RunPod URL shape.

The hosted image starts through `containers/live/entrypoint.sh`. It verifies
the retained archive before extracting it under `/models/quadruped`, generates
the capability-scoped controller from the image's own `play.py`, and launches
the selected checkpoint. Build it with `make live-image IMAGE=<registry-ref>`;
the NVIDIA base can be changed with the Docker build argument
`ISAAC_LAB_IMAGE` instead of changing the application wrapper.

## Battle scars (all verified this session — see `learnings/2026-07-26-isaac-go2.md`)

- **Per-frame polling is too slow through the RunPod HTTP proxy** (~0.7 s/request
  overhead → <1 fps). **MJPEG `multipart/x-mixed-replace` over one connection
  gets ~13 fps** through the same proxy. Use a stream, not polling.
- **The sim loop starves the HTTP thread (GIL).** Add a tiny `time.sleep(0.003)`
  per step and downscale frames (640×360, quality 55) so the web thread stays
  responsive.
- **RunPod proxy SSH runs an interactive shell and ignores arg-commands** — drive
  it via stdin, `ssh -tt`, and strip ANSI. Transfer files by base64 in ≤480-char
  chunks (the PTY truncates ~4 KB lines) and read the final partial `fold` line
  (`while read || [ -n "$ch" ]`).
