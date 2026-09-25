# Architecture Brief: Robot Zoo

**Date:** 2026-09-24
**Status:** promoted first-try reference application

## Outcome

Give a new Robium visitor an immediate interactive result: open a compact
native controller beside MuJoCo's standard viewer, see a robot moving, switch
among three robot categories, and take control without ROS, Docker, a GPU, or
a model checkpoint.

## System boundary

```text
Gradio embedded in native pywebview window
                    ↓
     authenticated multiprocessing bridge
                    ↓
            SimulationManager
                    ↓
          robot-specific controller
                    ↓
         MuJoCo model/data + native viewer
```

The controller and simulation use separate processes because both the desktop
webview toolkit and MuJoCo need a main-thread UI loop. The simulation process
alone owns `MjModel`, `MjData`, `mj_step()`, and viewer synchronization.

## Decisions

| Decision | Choice | Reason |
| --- | --- | --- |
| Viewer | `mujoco.viewer.launch_passive()` | Preserve MuJoCo's camera, selection, perturbation controls, and diagnostic panels |
| Controls | Local Gradio embedded with pywebview | Simple buttons and dropdowns without modifying MuJoCo or opening a browser |
| Desktop shell | Cocoa on macOS; Qt over X11/XWayland on Linux | Provide the same two-window native experience on qualified desktops |
| Layout | MuJoCo left, 390 px controller right | Keep simulation primary while controls remain visible |
| Initial panels | Rendering and Joint expanded | Useful first inspection without overwhelming the viewport |
| Models | Pinned Menagerie Panda, Stretch 3, and Go2 | Three recognizable robot categories with maintained provenance |
| Switching | Close/load/reopen viewer | Avoid replacing incompatible model/data under an active viewer |
| Panda motion | Position actuators plus damped least-squares Cartesian control | Real closed-loop arm motion with a simple planar target |
| Stretch motion | Shipped wheel velocity and joint position actuators | Direct base and arm interaction without ROS |
| Go2 motion | Torque-PD posture tracking | Stable poses without claiming an unprovided locomotion policy |

## Platform boundary

- macOS uses Cocoa/WebKit and AppKit/Quartz for tiling, focus, and MuJoCo's
  native section shortcuts.
- Linux uses Qt WebEngine plus Xlib/XTest. Ubuntu 24.04 x86_64 is verified
  under X11; XWayland uses the same `DISPLAY` interface.
- Pure Wayland without XWayland is explicitly unsupported in this release
  because deterministic cross-process positioning and shortcut delivery have
  not been verified there.

The layout helper reruns whenever robot switching creates a new viewer.

## Evidence required for claims

- All three pinned Menagerie models load and remain finite during bounded
  physics checks.
- Panda visibly changes hand position, Stretch tracks its lift target, and Go2
  remains upright under posture control.
- The controller and MuJoCo viewer open as separate, non-overlapping windows.
- Only Rendering and Joint begin expanded, and the same layout returns after a
  robot switch.
- Closing either surface terminates the other process without leaving a local
  server or simulation worker behind.

Automated physics and UI-contract tests do not replace a real desktop launch;
platform qualification must retain a screenshot and the stated host/session
conditions.

## Deferred

- Direct mouse-driven Cartesian targets in the controller.
- Gamepad input.
- Go2 walking or a learned locomotion policy.
- Obstacles, task scenes, website embedding, and hosted sessions.
