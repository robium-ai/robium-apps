# Architecture Brief: Robot Zoo

**Date:** 2026-10-07
**Status:** floating dual-stick controller

## Outcome

Give a new Robium visitor a visible robot result immediately: open a floating
Gradio controller over MuJoCo's full native viewer, see a robot moving,
switch among three robot categories, and take control without installing ROS,
Docker, or a GPU. Go2 uses a cached pretrained CPU policy.

## Decisions

| Decision | Choice | Reason |
| --- | --- | --- |
| Simulator | `mujoco.viewer.launch_passive()` | Reuses the full native UI, camera, selection, and perturbation interaction |
| App controls | Wide floating local Gradio page | Embeds analog sticks and standard Gamepad API input without forking MuJoCo |
| Environment | uv + Python 3.12 | Smallest reproducible boundary for MuJoCo on macOS and Linux |
| Models | Pinned Menagerie Panda/Go2 and bundled ROBOTIS TurtleBot3 Burger | Visual variety with maintained model provenance |
| Module boundary | Thread-safe `SimulationManager` API | Gradio never touches model/data; the simulation loop owns physics |
| Viewer UI | Standard left and right panels hidden initially | Keeps native diagnostics and actuator inspection available |
| Robot switching | Dropdown + Load; close/load/reopen viewer | Different state layouts make a clean reload safer than hot-swapping |
| Panda motion | Position actuators plus damped least-squares Cartesian control | Real closed-loop motion with a simple planar target |
| TurtleBot3 motion | Differential-drive body commands to shipped wheel velocity actuators | Manufacturer model, physical wheel contact, no ROS conversion |
| Go2 motion | Published MoE/CTS checkpoint + documented posture targets | Reuses trained locomotion; source, hash and model adaptation in [Go2 controller](go2-controller.md) |
| Input timeout | Manager zeros commands after 500 ms | Stop behavior survives a disconnected UI |

## First-slice evidence

- Every model must load from its pinned source (Menagerie package or bundled ROBOTIS model).
- Panda's hand must visibly change position during its automatic loop.
- TurtleBot3 must drive forward/reverse, turn both ways, stop, and reset.
- Go2 must remain upright above the floor under the posture controller.
- State and control arrays must remain finite during bounded checks.
- Gradio and the native viewer require a manual visual check because successful
  process launches are not evidence that either surface is usable.

## Floating window

The native window is resizable, has a pin-on-top toggle, and remembers its size
and position outside the repository. Window state is clamped to the current
display on macOS. Pointer displacement scales with rendered stick size; the
existing input timeout and neutral-before-rearm behavior are preserved.

## Deferred

- Direct mouse-drag Cartesian targets; this version uses circular sticks and
  MuJoCo body perturbation.
- Physical gamepad hardware verification.
- Variable-height walking, obstacles, and task scenes.
- Website embedding or hosted sessions.
