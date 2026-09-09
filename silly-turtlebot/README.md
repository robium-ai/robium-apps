# Silly TurtleBot

A TurtleBot 4 contest character that listens to navigation requests, moves with
Nav2, looks through its cameras, and takes its comedy responsibilities much more
seriously than its cleaning responsibilities.

The real app has three runtime parts:

- The containerized Gemini agent and Lichtblick console run on the operator
  computer and expose only bounded semantic tools.
- Native ROS 2 Humble, SLAM, Nav2, the laser, and the guarded motion/TTS bridge
  run on the TurtleBot 4 Raspberry Pi.
- The contest OAK-D runs through a small DepthAI container on the NVIDIA Orin.
  Its JPEG goes to Gemini and the browser without crossing ROS/DDS.

There is also a Docker simulation runtime using ROS 2 Jazzy, Gazebo Harmonic,
the official TurtleBot 4 simulator, Nav2, and its simulated OAK-D. It reuses the
pinned furnished-home world, matching occupancy map, and launch lessons from
[`robot-navigation`](../robot-navigation/), while retaining TurtleBot 4's own
MPPI navigation configuration.

The mock, live-Gemini/fake-robot, and Gazebo/Nav2/OAK-D simulation paths pass
locally. The real Humble robot is also deployed and verified without commanding
motion: scan, odometry, map, Nav2 lifecycle nodes, guarded actions, OAK-D
capture, the browser proxy, and offline TTS are live.

## Local quick start

```bash
./app build
./app demo
./app smoke
```

`./app smoke` runs seven critical tests: the end-to-end comedy mission, the
motion-authority guard, audio framing, Live API tool mediation, fresh-camera
handoff, the HTTP robot adapter, and the browser mission API contract.

## Gazebo furnished-home simulation

Docker is the reproducible ROS/Gazebo environment on macOS. Start Docker
Desktop, then run:

```bash
./app run
```

`run` follows the repository-wide app convention and defaults to the safe
simulation target. The equivalent explicit command is:

```bash
./app run --sim
```

For diagnostics and compatibility, the lower-level commands remain available:

```bash
./app sim-doctor
./app sim-up
./app sim-smoke
```

When the image is missing, the first `sim-up` downloads ROS 2 Jazzy packages
and the checksum-verified home asset, so it can take several minutes. Later
`sim-up` runs reuse those images; use `sim-build` when you intentionally want
to refresh them. `sim-up` starts the headless simulation and its guarded
Gemini mission service. The simulation contains Gazebo Harmonic, a standard
TurtleBot 4, localization, Nav2, an OAK-D JPEG stream, and the same semantic
bridge used by the physical robot.
It also bundles the same Lichtblick/Foxglove visualization path proven in
`robot-navigation`. Open <http://127.0.0.1:8091> for the OAK-D view, map,
laser scan, Nav2 plans, robot model, TF, and ROS logs. The semantic robot API
remains on <http://127.0.0.1:8088/v1/health>; port 8088 is not a web console.
The Gemini key stays in the agent service and is never sent to the browser.

The bundled map has three enabled names: `dock`, `kitchen`, and `living_room`.
After `run` (or `sim-up`), open <http://127.0.0.1:8091>, enter an instruction in **Silly
TurtleBot Mission Control**, and press **Run mission**. The panel includes
contest presets, a guarded-action transcript, **Dock**, **Undock**, and
**Stop robot**. No second terminal command is required.

To send an operator-selected Nav2 goal from Lichtblick, use the pose-publish
tool in the 3D panel and place the arrow in known free map space. The bundled
layout publishes a `geometry_msgs/PoseStamped` on `/goal_pose`, which the
running Nav2 `bt_navigator` subscribes to directly. This is direct operator
control: it bypasses Gemini's named-location guard, while Nav2 still plans and
checks the route against its costmaps.

Forward requests use a dedicated `move_forward(distance_m)` tool backed by
Nav2 `DriveOnHeading`. It accepts only 0.10–1.00 m and uses a fixed conservative
bridge speed; “go forward a little” defaults to 0.25 m. It does not publish raw
wheel velocities.

The CLI remains available for debugging or scripted runs:

```bash
./app sim-live --text "Go to the living room, look around, and comment."
```

`run`, `live`, and `sim-live` use `GEMINI_API_KEY` when it is already exported.
Otherwise the app loads it from Doppler internally: it prefers `robium/test`
when the current token can access it and uses `robium/dev` for a dev-scoped
token. `DOPPLER_CONFIG` remains an explicit override.

Useful controls:

```bash
./app camera --robot-url http://127.0.0.1:8088 --output gazebo-oakd.jpg
./app sim-logs
./app sim-down
```

The simulation models the TurtleBot's OAK-D but not the optional top camera.
It is headless by design; camera frames are available through `./app camera`
and are sent directly to Gemini during `sim-live`. The simulator acknowledges
the `speak` tool without playing audio; audible TTS is validated on the host or
physical robot.

## Test ladder

Keep the automated suite small and use the simulator for behavior:

1. `./app smoke`: seven fast checks for the mission guard, Live API mediation,
   audio framing, camera handoff, HTTP adapters, browser mission API, and mock mission.
2. `./app sim-up && ./app sim-smoke`: prove Gazebo, localization, all three
   Nav2 actions, named locations, a fresh OAK-D JPEG, and browser controls are
   ready.
3. Run bounded console missions: one look-and-comment turn, one named-room
   navigation and return, then the staged sock routine. A pass requires terminal
   Nav2 success, only declared tools, a fresh post-action frame, and a clean
   stop; readable tool transcripts are the acceptance evidence.
4. On hardware, run `robot-smoke` first because it commands no motion. Then,
   under supervision with the stop path ready, repeat one spin, one named goal,
   and the full contest routine three times. Camera freshness, stand-off
   distance, audible speech, and cancellation must all pass on the real robot.

## Live Gemini with the fake robot

```bash
./app live --text "Patrol the living room and report any mess."
```

The current model is `gemini-robotics-er-2-streaming-preview`. Audio files must
be raw signed 16-bit little-endian mono PCM at 16 kHz; image files must be JPEG.

## Real TurtleBot 4 + Orin OAK-D

Deploy the ROS/Nav2 service to the Pi and the USB camera service to the Orin:

```bash
./app robot-deploy ubuntu@ROBOT_IP
./app orin-camera-deploy USER@ORIN_IP
```

The Pi service starts SLAM, Nav2, the guarded bridge, and Foxglove after the
stock TurtleBot service. It also adds a retry policy for the robot's Wi-Fi boot
race and installs offline TTS. The Orin image contains its own pinned DepthAI
userspace driver, so it needs no host Python or ROS installation. This OAK-D is
held at USB High Speed because SuperSpeed firmware boot is unreliable with the
current Jetson; that still easily carries 640×360 at 12 fps.

Start the real control plane from the app directory:

```bash
./app run --real \
  --robot-url http://ROBOT_IP:8088 \
  --camera-url http://ORIN_IP:8081
```

This switches off any local simulator, starts the Gemini agent and Lichtblick,
and prints the console URL (normally <http://127.0.0.1:8091>). No second shell
or manual `doppler run` command is required. Use `./app real-down` to stop the
local control plane; the Pi and Orin services remain available for the next run.

The live system currently builds a SLAM map. Survey the real poses and edit
`robot/ros_ws/src/silly_turtlebot_ros/config/waypoints.yaml`. Every location is
disabled initially; the bridge refuses it until `configured: true` is set. A
convenient way to inspect the current map pose is:

```bash
ros2 run tf2_ros tf2_echo map base_link
```

For a future second top camera, make its driver publish
`sensor_msgs/msg/CompressedImage` and pass its topic to the bridge:

```bash
ros2 topic list -t | grep 'sensor_msgs/msg/CompressedImage'
./robot/run_bridge.sh \
  secondary_camera_topic:=/top_camera/image_raw/compressed
```

Real mode never falls back to the fake robot. `--robot-url` is required, while
`--camera-url` selects the Orin OAK-D. `./app live` remains the lower-level
one-turn diagnostic command.

## Safety and current limits

Gemini can request named navigation, bounded collision-checked forward motion,
Nav2 spins, explicit dock/undock, speech, and stop. It never receives raw
velocity, motor, map-coordinate, or arbitrary-pose tools. The ROS bridge also
refuses concurrent motions and cancels the active Nav2 goal on `stop`.

Object approach and person-facing are deliberately rejected on the real bridge
until RGB-depth grounding is implemented. The fake mission exercises those
beats, but the physical robot will currently navigate, look, comment, and stop.

Run `SILLY_CAMERA_URL=http://ORIN_IP:8081 ./robot/smoke.sh` on the Pi to verify
Nav2, scan, odometry, map, bridge, and OAK-D without commanding motion.

## Upstream references

- [TurtleBot 4 Jazzy simulator](https://turtlebot.github.io/turtlebot4-user-manual/software/turtlebot4_simulator.html)
- [TurtleBot 4 navigation](https://turtlebot.github.io/turtlebot4-user-manual/tutorials/navigation.html)
- [TurtleBot 4 OAK-D topic in the simulator bridge](https://github.com/turtlebot/turtlebot4_simulator/blob/jazzy/turtlebot4_gz_bringup/launch/ros_gz_bridge.launch.py)
- [Nav2 Humble `NavigateToPose`](https://api.nav2.org/actions/humble/navigatetopose.html)
- [Gemini Robotics streaming](https://ai.google.dev/gemini-api/docs/robotics-streaming)
