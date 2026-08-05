# indoor-navigation

A robot explores a world it has never seen, builds a map of it, then drives
itself to any goal you click — the classical autonomous-navigation pipeline
(SLAM → save the map → localize → plan → drive), running entirely in
simulation on a laptop. No GPU, no robot, no ROS installation on your
machine: everything runs headless inside one Docker image, and you watch it
live in your browser.

**Stack:** ROS 2 Jazzy · Nav2 · slam_toolbox · Gazebo Harmonic · TurtleBot 3
· Docker · Foxglove

## What you'll see

- **SLAM:** the robot drives a route while slam_toolbox builds an occupancy
  map from lidar in real time.
- **Autonomous navigation:** Nav2 localizes on the saved map (AMCL), plans a
  path around obstacles, and drives goals — sent programmatically or by
  clicking in Foxglove.
- All of it headless at real-time speed (RTF ≈ 1.0, software rendering), with
  live map/laser/path visualization in the browser.

## Prerequisites

- Docker (Desktop or compatible). Apple Silicon and other arm64 hosts work
  out of the box; the image is built from `ros:jazzy-ros-base-noble`.
- A browser. No local ROS, no display server, no accounts needed.

## Try it in 2 commands

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

- `make smoke` — the pass bar: launches the full nav scenario headless,
  sends two goals, exits 0 on success (~90 s once built)
- `make sim` — bringup only; `make slam` — rebuild the map; `make nav` —
  navigation without the demo auto-init (set the initial pose yourself)
- `make check` — preflight: Docker daemon, compose v2, port 8765 free
- `make check-map` — host-side map sanity check (`tests/check_map.py`)
- `make down` — tear down all profiles' containers

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
An archived IDE-workspace flavor of this demo (file tree, editor, PTY
terminal) lives in the private development repo.
