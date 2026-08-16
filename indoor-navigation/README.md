# Indoor Navigation

Run a complete mobile robot navigation stack on a laptop. TurtleBot3 Waffle Pi
maps a simulated environment, localizes on saved maps, plans around obstacles,
and drives to goals through a browser control panel.

No GPU, physical robot, or local ROS installation is required.

**Stack:** ROS 2 Jazzy, Nav2, slam_toolbox, Gazebo Harmonic, TurtleBot3,
Docker, and Lichtblick.

> **Media placeholder:** Add a hero image and short demo GIF in a separate pass.

## What you can do

- Map the House or Warehouse simulation.
- Save maps and load them for localization.
- Save the robot's current pose as a named waypoint.
- Navigate to saved waypoints or goals selected in the 3D view.
- Cancel navigation or stop robot motion from the Dashboard.
- Watch the camera, map, lidar, global plan, local plan, and ROS logs.

## Quick start

Install Docker Desktop or another Docker environment with Compose v2, then run:

```bash
cd indoor-navigation
make doctor
make build
make run
```

Open http://localhost:8080. The app starts in **IDLE** with Gazebo and the
robot running. SLAM and Nav2 start only when you begin mapping or load a map.

The first image build can take about 10 minutes. Later runs reuse that image,
so you only need to rebuild after changing the app, Dashboard, dependencies,
or simulation assets. Press Ctrl-C to stop a foreground run, or use
`make stop` from another terminal.

## Use the Dashboard

The default layout places the camera and 3D view across the top, ROS logs at
the bottom, and the Robium Dashboard on the right.

### Create a map

1. Choose **House** or **Warehouse** in Simulation. House is the default.
2. Enter a map name.
3. Select **Start mapping**.
4. Drive with WASD, the arrow keys, or the movement buttons.
5. Select **Finish mapping** to save the map and return to IDLE.

Changing the simulation stops the active mapping or localization session. Maps
are kept separate for each environment.

### Navigate and use waypoints

1. Select a saved map and choose **Load & localize**.
2. Set the robot's initial pose in the 3D view if localization needs it.
3. Enter a waypoint name and choose **Save position**.
4. Use **Navigate** beside a waypoint, or send a goal from the 3D view.

The Navigation section reports **Navigating** while a Nav2 goal is active.
**Stop navigation** cancels that goal. **Stop robot** also sends zero velocity,
but it is not a certified emergency stop.

### Read the visualization

- The global Nav2 plan is cyan.
- The local controller plan is orange.
- Log tabs show **All**, **Navigation**, and **Mapping & App** messages from
  `/rosout`.

If a plan is missing, open the 3D panel settings and confirm its topic is
visible. A plan appears only after Nav2 receives a goal and publishes one.

## Commands

Run `make help` for the current command list and equivalent `robium app`
commands.

| Command | Purpose |
| --- | --- |
| `make doctor` | Check Docker, Compose, ports, and image status |
| `make build` | Build the application image |
| `make run` | Start the simulator and control panel |
| `make status` | Show running services and URLs |
| `make logs` | Follow application logs |
| `make stop` | Stop application services |

Advanced modes are available for focused workflows:

| Mode | Purpose |
| --- | --- |
| `make sim` | Run the headless simulation without SLAM or Nav2 |
| `make slam` | Run the scripted mapping route and save a map |
| `make nav` | Start navigation on a saved map |
| `make demo` | Run the autonomous hosted-demo flow locally |

## Local data and shared assets

Saved maps and waypoint sidecars are local, untracked files. Waypoints are
stored beside their map as `<map>.waypoints.json`. The app never promotes or
deletes them automatically.

House and Warehouse are registered in the repository-wide asset catalog as
`world.aws-small-house` and `world.tugbot-warehouse`. Their source revisions,
checksums, entrypoints, and licenses are tracked under `shared/assets/`; large
payloads are downloaded during the image build. House uses the MIT-licensed
AWS RoboMaker Small House. Warehouse uses an upstream CC BY-NC-ND 4.0 asset,
so review its license before reuse.

## How it works

```text
Gazebo sensors and motion
          |
          v
ROS 2 + slam_toolbox + Nav2
          |
          v
foxglove_bridge and app services
          |
          v
Lichtblick + Robium Dashboard
```

The main workflow runs in one container. This avoids DDS multicast routing
problems across Docker containers on macOS. The image also bundles Lichtblick
and the Dashboard extension, so no manual extension installation is needed.

See [docs/architecture-brief.md](docs/architecture-brief.md) for the full
architecture and design decisions.

## Reuse the Dashboard

The Robium Dashboard is a configurable Lichtblick extension shared across
Robium apps. Other projects can install its `.foxe` package, enable the needed
sections, configure their ROS interfaces, and commit the resulting Lichtblick
layout.

Build the extension package with:

```bash
make dashboard-extension
```

See [shared/lichtblick-dashboard/README.md](../shared/lichtblick-dashboard/README.md)
for installation, configuration, customization, and safety details.

## Native macOS and external viewers

Apple Silicon Macs can run the ROS and Gazebo stack from an app-local
Pixi/RoboStack environment:

```bash
make native-setup
make demo-native
```

Use `make native-down` after an interrupted native session. Generated native
state stays under `experiments/native-macos/` and is ignored by Git.

To use another Foxglove-compatible viewer, connect it to
`ws://localhost:8765` while the app is running.

## Troubleshooting

- Run `make doctor` before the first build or after changing Docker settings.
- Run `make status` to confirm the app and dashboard endpoint are running.
- Run `make logs` to inspect Gazebo, ROS, bridge, and viewer output.
- Rebuild if source, dependencies, Dashboard code, or simulation assets changed.
- Use a private browser window at http://127.0.0.1:8080 to rule out saved
  Lichtblick settings from another session.

## More documentation

- [Architecture brief](docs/architecture-brief.md)
- [Project case study](docs/case-study.md)
- [Shared asset catalog](../shared/assets/README.md)
- [Robium Dashboard](../shared/lichtblick-dashboard/README.md)

## Live demo deployment

Maintainers can build and deploy the hosted demo with `make demo-image` and
`make demo-deploy`. This requires access to the Robium Google Cloud project and
is not part of the local setup.
