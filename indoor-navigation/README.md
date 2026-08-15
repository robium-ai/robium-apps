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

## Docker: run the app

```bash
make build   # one-time image build (about 10 min cold)
make run     # simulator + interactive control panel
```

Then open http://localhost:8080. The viewer (Lichtblick, the open-source
Foxglove fork bundled in the image) includes the robot camera, 3D map, ROS
logs, and Robot Control. The app starts in IDLE; start mapping or load a saved
map from the control panel. Ctrl-C stops the foreground process.

This is byte-for-byte the same container that powers the live demo at
robium.ai/demos/nav-trial: same simulation, same Nav2 stack, same viewer.

Note: nav goals are map-frame — the SLAM map origin is the robot's start
pose, so world (-2.0, -0.5) = map (0, 0).

## Commands

Run `make help` to see the standard Make commands and their equivalent
`robium app` commands. The lifecycle vocabulary is `help`, `doctor`, `build`,
`run`, `status`, `logs`, and `stop`.

- `make doctor` — diagnose Docker, Compose, ports 8080/8765, and image status
- `make status` — show running services and dashboard endpoints
- `make logs` — follow Docker, Gazebo, ROS, and viewer process output
- `make stop` — stop all application services

Advanced modes remain available: `make sim` runs simulation only;
`make slam` rebuilds a map through the scripted route; `make nav` starts raw
navigation without demo initialization; and `make demo` runs the autonomous
hosted-demo flow locally.

### Use the default control panel

The mapping layout reserves its right 24% for the **Robium Robot Control**
Lichtblick extension across the full dashboard height. On the left, the camera
and 3D map share the top row and ROS logs span the bottom row. The log area has
**All**, **Navigation**, and **Mapping & App** tabs; the grouped tabs filter the
shared `/rosout` stream by node name. The Docker image builds and preinstalls
the extension automatically; there is no drag-and-drop installation step for
indoor-navigation.

Start the control panel:

```bash
make run
```

Open http://localhost:8080. The right rail should immediately show Robot
Control with WASD, mapping, map-loading, named waypoints, and Stop Robot.
The 3D map draws the global Nav2 plan in cyan and the local controller plan
in orange. To
prove the default works independently of any previous browser installation,
open http://127.0.0.1:8080 in a private window; that is a clean browser origin.

To rebuild the reusable extension package, run:

```bash
make control-extension
```

The command prints the absolute path to
`shared/lichtblick-robot-control/robium.robot-control-0.8.0.foxe`. That artifact
remains reusable in other Lichtblick projects: drag it onto another project's
browser viewer (or use Lichtblick's file picker) and confirm installation once
for that browser origin. Indoor-navigation's committed layout supplies its ROS
defaults automatically.

The panel starts in **IDLE**: Gazebo and the robot are running, but SLAM,
map_server, AMCL, Nav2, and `/map` are not. **Start mapping** launches SLAM and
Nav2 for the entered name, locks that name, and changes to **Finish mapping**.
Finish mapping saves it beneath the selected world and tears that stack down;
**Load & localize** launches map_server, AMCL,
and Nav2 for a saved map. Only one navigation mode can run at a time.

The **Navigation** card reports **Navigating** while any Nav2 goal is active,
whether it came from a saved waypoint or the 3D map. **Stop navigation**
cancels that goal and is disabled while navigation is idle.

After **Load & localize**, enter a waypoint name and choose **Save position**
to capture the robot's current map-frame position and heading. Saved waypoints
for that map appear alphabetically with **Navigate** and **Delete** actions.
Navigate confirms that Nav2 received the stored goal; it does not claim the
robot has arrived. Waypoints are local per-map sidecars named
`<map>.waypoints.json` beside user-saved maps and are not committed by default.

The compact Simulation card offers **House** and **Warehouse**. House is the
default and uses the MIT-licensed AWS RoboMaker Small House asset, pinned and
prepared for modern Gazebo during the image build. Warehouse uses the pinned
OpenRobotics Tugbot warehouse and remains in Gazebo's local cache after its
first download. Restarting a world stops any mapping/localization session and
returns to IDLE. Maps remain grouped under the stable internal world names, so
only maps created for the active environment appear in the list.

TurtleBot3 Waffle Pi is the single controllable robot in both environments.
Its wider 0.15 m navigation radius, lidar, IMU, odometry, and pinhole camera
are used consistently by Gazebo, Nav2, and the dashboard. The Tugbot already
present in Warehouse remains part of the environment rather than a second
controllable robot.

Movement supports held WASD/arrow controls and adjustable forward/turn speed.
Stop Robot sends zero velocity and cancels active navigation; it is not a
hardware emergency stop.

External viewers still work too: with any scenario running, connect
Foxglove or a local Lichtblick to `ws://localhost:8765` (during `make demo`
the same port serves both the viewer and the WebSocket). The committed
layout for that flow is `foxglove/indoor-navigation-layout.json`.

## How it's put together

- Architecture and design rationale: `docs/architecture-brief.md`
- The demo image bundles the Lichtblick web viewer; the gateway serves it
  on :8765 alongside the Foxglove WebSocket tunnel and session API.
- One Docker image; compose profiles are the scenarios (sim / slam / nav /
  mapping / demo). All nodes of a scenario run in ONE container — macOS hosts
  can't route DDS multicast across containers.
- `make build` uses an explicit service name (`docker compose build sim`) —
  a bare `compose build` builds nothing when every service is behind a
  profile.
- Map regeneration: `make slam` rewrites `src/indoor_nav_bringup/maps/`
  (map.pgm + map.yaml) via the compose volume mount; the next image build
  (`make build`) bakes the new map in. The SLAM run is bounded by
  `SLAM_TIMEOUT` (default 900) inside the container.

## Live demo (maintainers)

`make demo-image` + `make demo-deploy` push the demo to
Cloud Run (`demo-nav-trial`, robium-prod, per-visitor instances, GZ_RELAY
unicast discovery), where robium.ai/demos/nav-trial hands each visitor a
private instance and embeds the instance-served viewer. Requires robium
GCP credentials — not needed for anything else in this app.
