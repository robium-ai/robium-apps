# Robot Zoo

Try three robots in MuJoCo from a small native controller—no ROS, Docker,
GPU, model checkpoint, account, API key, browser window, or MuJoCo fork.

![Robot Zoo running with the MuJoCo viewer and native controller side by side](assets/stills/robot-zoo-macos.png)

## What opens

`./app run` opens two native windows side by side:

1. **MuJoCo's standard viewer** with its camera controls, body interaction,
   rendering options, joints, actuators, and other diagnostic panels.
2. **Robot Zoo Controller**, a compact native window for selecting and moving
   a Franka Panda, Hello Robot Stretch 3, or Unitree Go2.

The controller uses a local Gradio page inside pywebview. It does not open a
browser or replace MuJoCo's viewer. Rendering and Joint are the only MuJoCo
sections expanded initially; every standard section remains available.

## Prerequisites

- macOS, or Ubuntu 24.04 x86_64 in an X11/XWayland desktop session
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Network access for the first build, which downloads locked Python packages
  and the three pinned MuJoCo Menagerie models

Ubuntu desktop installations normally provide the native libraries used by Qt
WebEngine. A minimal Ubuntu installation may need:

```bash
sudo apt install libnspr4 libnss3 libasound2t64 libcups2t64 libgbm1 \
  libxkbcommon-x11-0 libxcb-cursor0
```

X11 is verified directly; XWayland uses the same `DISPLAY` interface. Pure
Wayland without XWayland is not yet qualified. No GPU is required.

Check the host without installing anything:

```bash
./app doctor
```

The qualified Linux layout is captured in
[robot-zoo-linux.png](assets/stills/robot-zoo-linux.png).

## Quick start

From this directory:

```bash
./app build
./app run
```

The first command prepares the locked environment and caches the robot models.
Later runs reuse the local uv and Menagerie caches.

With Robium installed, the same path works from any directory:

```bash
npx robium-ai app check robot-zoo
npx robium-ai app run robot-zoo
```

You should see the Panda moving automatically, with MuJoCo on the left and the
controller on the right. Closing either window stops the complete application.

## Select and control a robot

| Control | Result |
| --- | --- |
| Robot + **Load** | Safely close the current viewer, load the selected model, and reopen MuJoCo |
| `↑` / `↓` | Move forward/back or adjust the robot-specific target |
| `←` / `→` | Turn, sway, or move the end-effector sideways |
| **Stop** | Zero the persistent movement command and hold |
| Speed | Scale current and future movement commands |
| Action + **Run action** | Run a robot-specific action |
| **Reset robot** | Return to the default automatic demo |

- **Franka Panda:** arrows move the Cartesian end-effector target in the XY
  plane. Actions raise/lower the target or open/close the gripper.
- **Stretch 3:** arrows command base velocity. Actions move the lift or arm.
- **Unitree Go2:** arrows adjust stand/crouch and lateral posture. Actions set
  Stand or Sit. This is posture control, not a locomotion-policy claim.

Movement continues until **Stop** is pressed. Controller callbacks only send
commands through the local bridge; they never manipulate `MjModel` or `MjData`.

## Use MuJoCo's mouse controls

- Drag in empty space to rotate or pan the camera; scroll to zoom.
- Double-click a body to select it.
- Ctrl-drag rotates the selected body.
- Ctrl-right-drag translates the selected body.
- Press `F1` for MuJoCo's complete built-in help.

The native actuator and visualization panels remain available for inspection.

## More commands

| Command | Purpose |
| --- | --- |
| `./app doctor` | Diagnose host, display, and installed-environment prerequisites |
| `./app run --robot stretch` | Start with Stretch 3 |
| `./app run --robot go2` | Start with Unitree Go2 |
| `./app viewer --robot panda` | Open only MuJoCo's standard viewer |
| `./app check` | Run bounded headless physics checks for all three robots |
| `./app smoke` | Test the launcher, UI contract, controllers, and models |

## Troubleshooting and cleanup

- **`uv` is missing:** install uv, then rerun `./app doctor`.
- **No Linux display:** run in a graphical X11 session or enable XWayland so
  `DISPLAY` is set. Remote headless shells cannot open the native windows.
- **A first build takes longer:** package and model downloads happen only on
  the first clean build.
- **A window closed unexpectedly:** close the other window and run
  `./app run` again. Robot switching should be done with **Load**.
- **Reset local dependencies:** remove `.venv`, then rerun `./app build`.

The app binds its authenticated command bridge and embedded controller server
only to `127.0.0.1`; sharing is disabled.

## Model sources and licenses

Models come from the pinned `mujoco-menagerie==2026.9.0` package and remain
under their upstream licenses:

- Franka Emika Panda — Apache-2.0
- Hello Robot Stretch 3 — Apache-2.0
- Unitree Go2 — BSD-3-Clause

Robot Zoo does not copy or modify those model packages. See
[MuJoCo Menagerie](https://github.com/google-deepmind/mujoco_menagerie) for the
model documentation, revisions, and license texts.

## Architecture boundary

```text
Native controller (Gradio in pywebview)
                    ↓
          authenticated local bridge
                    ↓
            SimulationManager
                    ↓
           robot controller
                    ↓
          MuJoCo native viewer
```

The simulation loop alone owns `mj_step()` and `viewer.sync()`. Switching a
robot closes the active viewer, creates new model/data, and opens a fresh
viewer rather than hot-swapping state underneath a live window. See the
[architecture brief](docs/architecture-brief.md) for the design and evidence
boundary.
