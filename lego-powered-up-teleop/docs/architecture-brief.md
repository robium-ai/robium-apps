# Architecture Brief: LEGO Powered Up Teleop

**Date:** 2026-09-14
**Status:** active

## Goal and constraints

Provide the smallest useful real-robot slice for a LEGO differential-drive base:
a Python window on the maintainer's Mac with hold-to-drive forward, reverse,
left, right, and stop controls. The robot has two LEGO Powered Up motors and a
Bluetooth hub. Exact hub model and motor ports remain provisional until the
first hardware smoke.

The first slice does not use ROS 2, localization, a camera, autonomy, or a
simulator. It must fail stopped if the window closes, Python crashes, or the BLE
link disappears.

## Decisions

| Decision | Choice | Why now | Confidence |
|---|---|---|---|
| First working slice | Native directional pad plus BLE motor control | Proves the physical command path before the full-scale application adds sensors or autonomy | approved |
| Hub runtime | Reversible Pybricks firmware with a saved bridge program | Supported hubs expose a documented computer-to-hub BLE path and can enforce the watchdog beside the motors | validated on the connected `Pybricks Hub` |
| Host UI | Pygame window with mouse, keyboard, and hot-plugged SDL gamepad controls | Supports hold/release events without a browser; Stadia left-stick throttle, right-stick steering, D-pad, A-stop, center deadzone, and removal-to-zero behavior are hardware-free tested | `Google Stadia Controller` detected over Bluetooth; live control still needs wheels-up confirmation |
| Environment | uv, Python 3.12, committed lockfile | Pure Python; the locked environment resolves and all checks pass on the Apple Silicon host | validated |
| Motor protocol | Fixed three-byte left/right duty command at 10 Hz | Small enough for BLE, permits speed control and future higher-level driving; encode/decode, mixing, framing, and clean-stop writes are tested | validated without hardware |
| Stop behavior | Zero on release/exit plus a 400 ms hub watchdog | The hub still stops when the host is the failed component | high |

## Module boundaries and communications

| Module | Rate / failure domain | Boundary |
|---|---|---|
| Pygame UI | 30 Hz; may close, lose focus, or lose its gamepad independently | Resolves stop overrides and mouse/keyboard/Stadia inputs, then writes the latest normalized throttle/steer into an in-process `DriveSession` |
| BLE worker | 10 Hz; adapter/link errors must not freeze the UI | Sends Pybricks `WRITE_STDIN` messages and reports connection state back to the UI |
| Pybricks hub bridge | 10 ms watchdog loop; must remain safe if the Mac disappears | Decodes `D,left,right`, drives the two motors, and brakes after 400 ms without a drive packet |

## Provisional assumptions and risks

| Assumption or risk | Impact | Cheapest validation | Authorized pivot |
|---|---|---|---|
| Hub is City, Technic, Essential, or Prime/Inventor rather than BOOST Move or Technic Move | Unsupported hub would not run this stdin bridge or accept Pybricks | Identify hub and install Pybricks | Use stock LEGO Wireless Protocol for an unsupported hub without changing the UI/session boundary |
| Motors are on ports A and B | **Validated:** both initialized and the bridge reached `READY`; after the hub direction correction, steering was correct but forward/reverse remained inverted, so only host throttle is now inverted | Repeat wheels-up directional check with the calibrated host control | Edit one motor direction constant only if a single wheel remains reversed |
| Ten BLE writes per second are reliable on the local Mac | Lag or disconnects would make driving poor | Drive at the default 35% power beside the laptop | Reduce control rate while keeping it well inside the 400 ms watchdog |
| Stadia Bluetooth mapping uses left Y axis 1 and right X axis 2, with up reported negative | A different firmware/platform mapping could swap an axis | Run `./app gamepad` and verify signed throttle/steer without connecting the robot | Expose axis selection flags while retaining the same gamepad/session boundary |

## Implementation path

1. **Done 2026-09-14:** installed Pybricks, saved `hub/main.py`, and passed the stopped `READY` plus PING/PONG hardware smoke.
2. Lift the wheels and verify forward/reverse/turn directions at the 35% cap.
3. Drive on a clear floor; treat sensors, camera, recording, and autonomy as later slices.
