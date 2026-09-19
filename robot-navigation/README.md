# Robot Navigation

Run a complete mobile robot navigation stack on a laptop. TurtleBot3 Waffle Pi
maps a simulated environment, localizes on saved maps, plans around obstacles,
and drives to goals through a browser control panel.

No GPU, physical robot, or local ROS installation is required.

**Stack:** ROS 2 Jazzy, Nav2, slam_toolbox, Gazebo Harmonic, TurtleBot3,
Docker, and Lichtblick.

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
cd robot-navigation
./app doctor
./app run
```

Open http://localhost:8080. The app starts in **IDLE** with Gazebo and the
robot running. SLAM and Nav2 start only when you begin mapping or load a map.

The first image build can take about 10 minutes. Later runs reuse that image,
so you only need to rebuild after changing the app, Dashboard, dependencies,
or simulation assets. `./app run` builds the image automatically when it is
missing. Press Ctrl-C to stop a foreground run, or use `./app stop` from
another terminal.

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

Run `./app help` for the current command list. The repository-local launcher
is a command interface; it starts Docker Compose services and does not require
Make.

| Command | Purpose |
| --- | --- |
| `./app doctor` | Check Docker, Compose, ports, and image status |
| `./app build` | Build the application image explicitly |
| `./app run` | Build if needed, then start the simulator and control panel |
| `./app status` | Show running services and URLs |
| `./app logs` | Follow application logs |
| `./app stop` | Stop application services |

Advanced modes are available for focused workflows:

| Mode | Purpose |
| --- | --- |
| `./app sim` | Run the headless simulation without SLAM or Nav2 |
| `./app slam` | Run the scripted mapping route and save a map |
| `./app nav` | Start navigation on a saved map |
| `./app demo` | Run the Cloud Run launch path locally on port 8765 |

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

### Simulation speed

Everything renders on the CPU — there is no GPU in this app, so Gazebo's
`ogre2` renderer falls back to llvmpipe and every sensor frame is rasterized
in software. The demo targets real time, because real-time factor is what
makes teleop feel right: at RTF 0.25 a TurtleBot commanded to 0.2 m/s appears
to crawl at 5 cm/s. Four settings hold it there, and each is worth
understanding before changing it:

- **Physics: a 4 ms step at 288 Hz, capped at `real_time_factor` 1.15**
  (`tune_physics()` in `sim.launch.py`). The pinned AWS house asset ships
  Gazebo Classic's 1 ms / 1000 Hz defaults, which this demo cannot afford.
  The 1.15 cap is not a typo — see below.
- **Camera at 4 Hz** (patched into the Waffle Pi SDF at image build time).
  Camera *rate* is a top cost; camera *resolution* is nearly free, because
  the cost is scene traversal rather than rasterization (320x240 measured
  0.521 against 640x480 at 0.522).
- **Lidar at 5 Hz.** `gpu_lidar` renders the scene exactly as the camera
  does, and halving it buys more than slowing the camera further. 5 Hz is a
  floor with a reason: the Nav2 local costmap updates at 5 Hz and
  slam_toolbox's `minimum_time_interval` is 0.5 s, so nothing downstream
  consumes scans faster.
- **The browser reads the camera as JPEG**, not raw. The Lichtblick layouts
  name `/camera/image_raw/compressed`, which `ros_gz_image`'s bridge
  advertises for free through `image_transport`. Raw RGB8 is 922 KB per
  frame; compressed measured 52 KB.

**Why the cap is 1.15 and not 1.0.** `real_time_factor` is a throttle, not a
target. Gazebo paces itself with sleeps and does not make them up after a
render stall, so a cap of exactly 1.0 settles at 0.92. Capping just above the
goal is what delivers it. It is also the only knob that binds: with the
factor left at the asset's 1, raising `real_time_update_rate` to 500 or
disabling it entirely both measured exactly RTF 1.000 — modern Gazebo does
not derive the factor from step x rate the way Classic did.

Measured on 8 CPUs in the House world with a live camera subscriber:
**RTF 1.02, steady within +/-0.01 across six windows, 269% CPU, 229 KB/s of
camera** — against 0.52, 377%, and roughly 4.7 MB/s before this work. On the
wire that is 5.8 Hz of `/scan`, 4.1 Hz of camera, and 47 Hz of IMU. Commanded
0.2 m/s tracked at 0.199 m/s with 0.0004 m/s velocity jitter, so the coarser
step costs no drive fidelity.

The uncapped ceiling in this configuration is 1.35, so the cap is doing the
pacing rather than the hardware — which is why the result is stable rather
than drifting. Headroom is what that spare 0.35 buys: slower hosts land
lower, and a Cloud Run vCPU is materially slower than a development Mac.

Two knobs that look promising and are not: Ogre 1.x (`render_engine` `ogre`)
is ~30% cheaper in principle but requires an X display and throws
`Couldn't open X display` under `--headless-rendering`, so only `ogre2` works
here. And decorative-mesh collision stripping — all 66 house models use full
trimesh collisions — is worth 11% at a 1 ms step and nothing at all once the
step is 4 ms.

`foxglove/robot-navigation-layout.json` deliberately stays on the raw topic.
It is imported into an external viewer over `ws://localhost:8765`, where
bandwidth is local and free, and raw works in both the Docker and native
Pixi/RoboStack environments — the compressed topic exists only where
`image_transport_plugins` is installed.

### Layout changes reach an existing browser

Lichtblick persists the layout in IndexedDB, so the layout bundled into
`index.html` is consulted only when the browser has none of its own. Without
help, a shipped layout change stays invisible to anyone who has opened the
page before — the old view keeps appearing until they clear site data. (HTTP
caching is not the culprit; the gateway already sends `Cache-Control:
no-cache`.)

`scripts/bundle_default_extension.py` injects a bootstrap that writes the
bundled layout straight into that store, guarded by a revision in
`localStorage`. The revision is a hash of the layout the page actually
carries, computed in the browser rather than baked in at build time, because
`scripts/viz_server.py` re-reads its layout file on every request so it can be
edited live — a build-time hash would go stale immediately.

The result is the rule you want: **the page starts from the layout file, and
only re-installs when that file changes.** A layout a user rearranged and
saved themselves survives every reload until a different one is shipped.

The IndexedDB database name, object store, and key path are tied to the
Lichtblick image digest pinned in `docker/Dockerfile`. Re-verify them whenever
that digest moves; the bootstrap fails soft (a `console.warn`, and Lichtblick
still loads) rather than breaking the page.

## Reuse the Dashboard

The Robium Dashboard is a configurable Lichtblick extension shared across
Robium apps. Other projects can install its `.foxe` package, enable the needed
sections, configure their ROS interfaces, and commit the resulting Lichtblick
layout.

Build the extension package with:

```bash
./app dashboard-extension
```

See [shared/lichtblick-dashboard/README.md](../shared/lichtblick-dashboard/README.md)
for installation, configuration, customization, and safety details.

## Native macOS and external viewers

Apple Silicon Macs can run the ROS and Gazebo stack from an app-local
Pixi/RoboStack environment:

```bash
./app native-setup
./app demo-native
```

Use `./app native-down` after an interrupted native session. Generated native
state stays under `experiments/native-macos/` and is ignored by Git.

To use another Foxglove-compatible viewer, connect it to
`ws://localhost:8765` while the app is running.

## Troubleshooting

- Run `./app doctor` before the first run or after changing Docker settings.
- Run `./app status` to confirm the app and dashboard endpoint are running.
- Run `./app logs` to inspect Gazebo, ROS, bridge, and viewer output.
- Rebuild if source, dependencies, Dashboard code, or simulation assets changed.
- Use a private browser window at http://127.0.0.1:8080 to rule out saved
  Lichtblick settings from another session.

## More documentation

- [Architecture brief](docs/architecture-brief.md)
- [Project case study](docs/case-study.md)
- [Shared asset catalog](../shared/assets/README.md)
- [Robium Dashboard](../shared/lichtblick-dashboard/README.md)

## Live demo

Try the public application at
[robium.ai/demos/robot-navigation](https://robium.ai/demos/robot-navigation/).
It creates one private, temporary Cloud Run service only after you press Start,
then removes it when you press Stop or after 30 minutes.

Maintainers can publish the application image with `./app demo-image`. The
controller, cleanup scheduler, and website deployment live in the sibling
`robium-website` repository. Cloud deployment is not part of local setup.
