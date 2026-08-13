# indoor-navigation

A robot explores a world it has never seen, builds a map of it, then drives
itself to any goal you click — the classical autonomous-navigation pipeline
(SLAM → save the map → localize → plan → drive), running entirely in
simulation on a laptop. No GPU, no robot, no ROS installation on your
machine. The portable path runs headless inside one Docker image; Apple
Silicon Macs can also run the same ROS/Gazebo stack from an app-local
Pixi/RoboStack environment with a native Metal-rendered Gazebo window.

**Stack:** ROS 2 Jazzy · Nav2 · slam_toolbox · Gazebo Harmonic · TurtleBot 3
· Docker or Pixi/RoboStack · Lichtblick

## What you'll see

- **SLAM:** the robot drives a route while slam_toolbox builds an occupancy
  map from lidar in real time.
- **Autonomous navigation:** Nav2 localizes on the saved map (AMCL), plans a
  path around obstacles, and drives goals — sent programmatically or by
  clicking in Foxglove.
- Native Gazebo on Apple Silicon, or headless simulation in Docker, with live
  map/laser/path visualization in the browser.

## Native macOS (Apple Silicon)

The native path opens Gazebo for the simulator scene and Lichtblick for ROS
state, navigation goals, and the robot-mounted camera. It
does not install Homebrew packages or a system ROS distribution.

```bash
make native-setup  # one-time app-local dependency + viewer install
make demo-native   # build, launch Gazebo + Lichtblick, stay in foreground
```

Press Ctrl-C to stop the owned process group. If a terminal was interrupted
before cleanup, run `make native-down`. All generated state remains under
`experiments/native-macos/` and is ignored by Git. This path supports macOS
arm64; use Docker for portable and Cloud Run-compatible execution.

## Docker prerequisites

- Docker (Desktop or compatible). Apple Silicon and other arm64 hosts work
  out of the box; the image is built from `ros:jazzy-ros-base-noble`.
- A browser. No local ROS, no display server, no accounts needed.

## Docker: try it in 2 commands

```bash
make build   # one-time image build (about 10 min cold)
make demo    # full stack: sim + Nav2 + built-in browser viewer
```

Then open http://localhost:8765 in your browser. The viewer (Lichtblick,
the open-source Foxglove fork, bundled in the image) auto-connects and
shows the map, laser scan, and planned paths. Click a navigation goal with
the 3D panel's pose-publish tool and watch the robot drive itself. Ctrl-C
stops everything.

This is byte-for-byte the same container that powers the live demo at
robium.ai/demos/nav-trial: same simulation, same Nav2 stack, same viewer.

Note: nav goals are map-frame — the SLAM map origin is the robot's start
pose, so world (-2.0, -0.5) = map (0, 0).

## Other scenarios

- `make mapping` — interactive SLAM, teleop, save/reset controls, and robot
  camera at http://localhost:8080
- `make localize` — AMCL localization on a saved map with load controls and
  clicked Nav2 goals at http://localhost:8080
- `make smoke` — the pass bar: launches the full nav scenario headless,
  sends two goals, exits 0 on success (~90 s once built)
- `make sim` — bringup only; `make slam` — rebuild the map; `make nav` —
  navigation without the demo auto-init (set the initial pose yourself)
- `make check` — preflight: Docker daemon, compose v2, port 8765 free
- `make check-map` — host-side map sanity check (`tests/check_map.py`)
- `make down` — tear down all profiles' containers

### Install the reusable control panel

The mapping layout reserves its right 28% for the **Robium Robot Control**
Lichtblick extension. Build and verify the extension from this app with:

```bash
make control-extension-check
```

The command prints the absolute path to
`shared/lichtblick-robot-control/robium.robot-control-0.1.0.foxe`. Drag that
file onto the Lichtblick browser window (or open it from the file picker) and
confirm installation once per browser origin. The committed mapping layout
then supplies the app defaults automatically.

The panel provides hold-to-drive WASD/arrow controls, mapping start/save,
available-map loading for localization, Stop Robot, and an intentionally
disabled Go Home button until a service is configured. Stop Robot sends zero
velocity; it is not a hardware emergency stop. Loading a map does not change
a running mapping launch graph into localization—start `make localize` for the
localization stack.

External viewers still work too: with any scenario running, connect
Foxglove or a local Lichtblick to `ws://localhost:8765` (during `make demo`
the same port serves both the viewer and the WebSocket). The committed
layout for that flow is `foxglove/indoor-navigation-layout.json`.

## How it's put together

- Architecture and design rationale: `docs/architecture-brief.md`
- The demo image bundles the Lichtblick web viewer; the gateway serves it
  on :8765 alongside the Foxglove WebSocket tunnel and session API.
- One Docker image; compose profiles are the scenarios (sim / slam / nav /
  test / demo). All nodes of a scenario run in ONE container — macOS hosts
  can't route DDS multicast across containers.
- `make build` uses an explicit service name (`docker compose build sim`) —
  a bare `compose build` builds nothing when every service is behind a
  profile.
- Map regeneration: `make slam` rewrites `src/indoor_nav_bringup/maps/`
  (map.pgm + map.yaml) via the compose volume mount; the next image build
  (`make build`, or `make smoke`'s `--build`) bakes the new map in.
- Timeouts: the smoke run is bounded by `SMOKE_TIMEOUT` (seconds, default
  180 ≈ 90 s sim × 2 at RTF ≈ 1.0) — override with e.g. `SMOKE_TIMEOUT=300
  make smoke`. The SLAM run has an analogous `SLAM_TIMEOUT` (default 900)
  inside the container.

## Live demo (maintainers)

`make demo-smoke` gates the demo scenario (viewer served, session guards,
one goal, shutdown). `make demo-image` + `make demo-deploy` push it to
Cloud Run (`demo-nav-trial`, robium-prod, per-visitor instances, GZ_RELAY
unicast discovery), where robium.ai/demos/nav-trial hands each visitor a
private instance and embeds the instance-served viewer. Requires robium
GCP credentials — not needed for anything else in this app.
