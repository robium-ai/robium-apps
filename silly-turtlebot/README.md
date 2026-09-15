# Silly TurtleBot

A TurtleBot 4 physical-AI demo that listens to free-form navigation requests,
moves with Nav2, and reasons proactively over its live camera and robot state.

The real app has three runtime parts:

- The containerized Gemini agent and Lichtblick console run on the operator
  computer and expose only bounded semantic tools.
- Native ROS 2 Humble, mapless Nav2, the laser, and the guarded motion/TTS
  bridge run on the TurtleBot 4 Raspberry Pi.
- The contest OAK-D runs through a small DepthAI container on the NVIDIA Orin.
  Its JPEG goes to Gemini and the browser without crossing ROS/DDS.

There is also a Docker simulation runtime using ROS 2 Jazzy, Gazebo Harmonic,
the official TurtleBot 4 simulator, Nav2, and its simulated OAK-D. It reuses the
pinned furnished-home world, matching occupancy map, and launch lessons from
[`robot-navigation`](../robot-navigation/), while retaining TurtleBot 4's own
MPPI navigation configuration.

The mock, live-Gemini/fake-robot, and Gazebo/Nav2/OAK-D simulation paths pass
locally. The real Humble robot is also deployed and verified without commanding
motion: scan, odometry, rolling costmaps, Nav2 lifecycle nodes, guarded actions, OAK-D
capture, the browser proxy, and offline TTS are live.

## Local quick start

```bash
./app build
./app demo
./app smoke
```

`./app smoke` runs twelve fast tests, including the end-to-end mock mission,
motion-authority guard, audio framing, Live API tool mediation, compact
heartbeat filtering, persistent session reuse, duplicate-call safety,
fresh-camera handoff, the HTTP robot adapter, and the asynchronous SSE mission
contract.

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
`robot-navigation`. Open <http://localhost:8091> for the control panel's OAK-D
view plus the 3D map, laser scan, Nav2 plans, robot model, TF, and ROS logs. A
second raw-image panel is intentionally omitted. The semantic robot API
remains on <http://127.0.0.1:8088/v1/health>; port 8088 is not a web console.
The Gemini key stays in the agent service and is never sent to the browser.

The bundled map has three enabled names: `dock`, `kitchen`, and `living_room`.
After `run` (or `sim-up`), open <http://localhost:8091>, enter an instruction in
**Silly TurtleBot Mission Control**, and press **Run mission**. The deliberately
minimal panel contains only the instruction field, **Run mission**, **Stop
robot**, the robot-status pill, and the timestamped rolling agent log. No second
terminal command is required. The bundled default layout keeps Mission Control
on the left, the 3D navigation view in the center, and the OAK-D Image panel
above Teleop on the right. The viewer serves assets with `no-store` and embeds
separate extension and layout revisions. An extension rebuild cache-busts the
loaded code; a changed bundled layout updates and selects one canonical
Lichtblick layout record once, preserving other saved layouts and normal edits
between layout releases.

Mission submission now returns immediately while the same Gemini Robotics
Streaming connection remains open across instructions. The panel shows model
text and guarded tool progress as SSE events arrive. During an active mission,
the instruction stays editable and **Run mission** becomes **Update mission**;
submitting replaces the active high-level instruction without sending every
keystroke. **Stop robot** stays available, closes the current Gemini turn, drops
queued camera/heartbeat input, and calls the guarded physical stop path. Fresh
OAK-D frames are supplied to Gemini at no more than 1 FPS while a mission is
active. A separate robot-side ROS node fetches the bandwidth-reduced 320x180
preview from the Orin at 1 FPS and publishes it as
`sensor_msgs/msg/CompressedImage` on
`/orin/oakd/preview/image_raw/compressed`. The bundled Lichtblick layout shows
that topic in its regular Image panel. The relay runs in
its own process and uses the reliable QoS expected by the robot's Foxglove
bridge, so an HTTP camera stall cannot block navigation callbacks. The full
640x360 frame remains available to Gemini. Frames and local
`tool.progress` events continue while a long Nav2 tool runs; model-facing text
heartbeats wait until no turn or blocking tool is unresolved. The original
blocking response is sent exactly once when the ROS action finishes;
conflicting calls are rejected and shown in the timestamped rolling log. An
unexpected Gemini cancellation stops the robot and fails the mission rather
than retrying partial motion. A Gemini `turn_complete` ends one reasoning turn,
while `complete_task` ends the mission.

To send an operator-selected Nav2 goal from Lichtblick, use the pose-publish
tool in the 3D panel and place the arrow in known free space. The bundled
layout publishes a `geometry_msgs/PoseStamped` in `odom` on `/goal_pose`, which
the running Nav2 `bt_navigator` subscribes to directly. This is direct operator
control: it bypasses Gemini's named-location guard, while Nav2 still plans and
checks the route against its lidar-fed costmaps. On the real robot, keep goals
within about 3 m so the complete route begins inside its 8 m rolling window.
The physical robot must be undocked first; the mission panel shows the live
dock state. In the 3D view, the rolling costmap and all plans are displayed in
`odom`: the global path is green, the smoothed path cyan, and local plan orange.
Lichtblick's Pose tool uses two clicks: click once for the goal position, move
the pointer to choose its orientation, then click again to publish. A drag that
leaves the toolbar saying **Click to cancel** has not sent a goal yet.
If the viewer was already open while its container was rebuilt, reload that tab
once before publishing; its patched JavaScript bundle is served with caching
disabled so subsequent rebuilds cannot leave an obsolete publisher loaded.

Distance requests use `move_distance(distance_m, speed_mps)` backed by the
Create 3 `DriveDistance` action for both forward and reverse motion. This bypasses
Nav2's lidar-costmap collision projection; the guarded distance and speed bounds
still apply. Angle requests use collision-checked Nav2 `rotate_by(angle_deg)`.
Bounded speed-plus-time translation and rotation use Nav2 `AssistedTeleop`.
Robot state includes dock state, active motion, odometry,
velocity, battery percentage, camera freshness, calibrated horizontal/vertical
FOV, and mount
offsets. Gemini receives camera geometry once at mission start, then a compact
idle-only heartbeat containing motion/velocity, dock state, and exceptional
alerts. During a blocking action, images and local progress logs continue but
heartbeat text waits for the terminal tool response. Full state is available
through `get_robot_state` between blocking actions, and action-completion
responses include compact final motion, dock, and odometry state.

Set `OAKD_MOUNT_YAW_DEG` and `OAKD_MOUNT_PITCH_DEG` on the Orin when the
camera is not aligned with the robot's forward horizontal axis. Stream FOV is
computed from the device calibration rather than assumed from a nominal spec.

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

1. `./app smoke`: twelve fast checks for the mission guard, Live API mediation,
   compact heartbeat filtering, persistent-session reuse, replay-safe tool
   calls, audio framing, camera handoff, HTTP adapters, asynchronous SSE mission
   API, and mock mission.
2. `./app sim-up && ./app sim-smoke`: prove Gazebo, localization, all three
   Nav2 actions, named locations, a fresh OAK-D JPEG, and browser controls are
   ready.
3. Run bounded console missions: rotate toward a visible object, move a short
   measured distance, and follow one open-ended room instruction. A pass
   requires terminal Nav2 success, only declared tools, continued frames and
   local progress during motion, no in-motion text heartbeat, a fresh
   post-action frame, and a clean stop; readable timestamped transcripts are
   the acceptance evidence.
4. On hardware, run `robot-smoke` first because it commands no motion. Then,
   under supervision with the stop path ready, repeat one spin, one named goal,
   and the full proactive navigation loop three times. Camera freshness, stand-off
   distance, audible speech, and cancellation must all pass on the real robot.

## Live Gemini with the fake robot

```bash
./app live --text "Patrol the living room and report any mess."
```

The current model is `gemini-robotics-er-2-streaming-preview`. Audio files must
be raw signed 16-bit little-endian mono PCM at 16 kHz; image files must be JPEG.

## Real TurtleBot 4 + Orin OAK-D

Deploy the ROS/Nav2 service to the Pi and the OAK-D plus neural-speech services
to the Orin:

```bash
./app robot-deploy ubuntu@ROBOT_IP
./app orin-camera-deploy USER@ORIN_IP
```

The Pi service starts mapless Nav2, the guarded bridge, and Foxglove after the
stock TurtleBot service. Nav2 plans in `odom` with rolling local and global
costmaps fed by the lidar; no map server, AMCL, or SLAM process is required. It
also adds a retry policy for the robot's Wi-Fi boot race. The Foxglove bridge
uses a 16-message live-view backlog instead of its 1,024-message default. If
Wi-Fi or browser rendering stalls, old camera, scan, and transform messages are
dropped so Lichtblick resumes at the robot's current view rather than replaying
seconds of stale frames. The Orin runs three
independent containers: the gamepad forwarder, pinned DepthAI OAK-D server,
on port 8081 and Kokoro-82M neural TTS on port 8082. This OAK-D is held at USB
High Speed because SuperSpeed firmware boot is unreliable with the current
Jetson; that still easily carries 640×360 at 12 fps.

Connect the contest speaker to the **Orin**, preferably over USB. The TTS
service automatically selects an ALSA USB speaker. HDMI/DisplayPort and unusual
devices should be set explicitly as `plughw:CARD,DEVICE` in `orin/.env`. The
default voice is the playful American-English `am_puck` at 1.03× speed;
`KOKORO_VOICE` and `KOKORO_SPEED` are deployment overrides. Playback adds
500 ms of leading silence to wake a sleeping USB speaker before the first
phoneme and 100 ms of trailing silence. Override these with
`TTS_LEADING_SILENCE_MS` and `TTS_TRAILING_SILENCE_MS` if needed.

Start the real control plane from the app directory:

```bash
./app run --real \
  --robot-url http://ROBOT_IP:8088 \
  --camera-url http://ORIN_IP:8081
```

This switches off any local simulator, starts the Gemini agent and Lichtblick,
and prints the console URL (normally <http://localhost:8091>). No second shell
or manual `doppler run` command is required. Use `./app real-down` to stop the
local control plane; the Pi and Orin services remain available for the next run.
When `--camera-url` is present, the agent automatically uses the same Orin host
on port 8082 for speech. Pass `--tts-url` only when speech is hosted elsewhere.

The console includes the same hold-to-drive motion pad as the TurtleBot 4
teleoperation reference app. It publishes `/cmd_vel` at 5 Hz with 0.15 m/s
linear and 0.4 rad/s angular limits; releasing the button publishes a stop.
This is a supervised manual override and is separate from Gemini's guarded
Nav2 tools. Keep the robot in sight and the floor clear while using it.

The physical robot also uses TurtleBot 4's stock, always-on joystick stack.
Pair the Bluetooth controller to the **Orin once**; the Orin radio supports the
Stadia controller reliably, while this TurtleBot Pi's onboard radio drops its
BLE handshake. A restart-persistent Orin container forwards only joystick
snapshots to the Pi, where a watchdog republishes them on the stock `/joy`
topic. It works whenever the robot computers boot, without the browser or an
operator-side `./app` process.

Joystick packets are sent over both a dedicated Ethernet link and Wi-Fi. The
direct link uses Pi `eth0` at `10.42.0.1/30` and Orin `enP8p1s0` at
`10.42.0.2/30`; neither profile installs a default route or DNS. Wi-Fi remains
an automatic fallback, so the controller works with no Internet and continues
through a failure of either one of the two local paths. Both Ethernet profiles
must be named `silly-direct`, set to autoconnect, and use the addresses above.

The existing controls remain unchanged: hold L1 while using the sticks for
normal driving, or R1 for the stock turbo mode. This app adds two spare Stadia
face-button actions: **A undocks** and **B docks**. Release L1 and R1 before
pressing either face button; dock/undock is deliberately ignored while a
drive-enable shoulder is held. If Orin packets stop for 350 ms, the Pi publishes
a neutral command so a lost controller cannot leave motion latched.

The contest robot's Create 3 base uses `safety_override: "full"`, as explicitly
requested for this application. This disables every cliff response and raises
the base speed limit. Operate only on a known level floor, keep it away from
stairs and drop-offs in every direction, and keep the physical stop path ready.
The Stadia sticks remain proportional through the stock TurtleBot teleop
scales; a rescaled 8% center deadzone removes drift without creating a fixed
speed step.

One-time pairing on the Orin uses its normal Bluetooth manager:

```bash
bluetoothctl
scan on
pair CONTROLLER_MAC
trust CONTROLLER_MAC
connect CONTROLLER_MAC
```

After pairing, `./app robot-deploy ubuntu@ROBOT_IP` installs the watchdog and
button mapper in the boot-enabled Pi service. `./app orin-camera-deploy
USER@ORIN_IP` installs the restart-persistent joystick, camera, and speech
containers. `./app robot-smoke ubuntu@ROBOT_IP` verifies the stock velocity
mapper, remote joystick receiver, dock-button mapper, and OAK-D preview relay
without moving the robot.

Check both Orin services without speaking:

```bash
curl http://ORIN_IP:8081/health
curl http://ORIN_IP:8082/health
```

The live system intentionally has no persistent room map. Its `odom` origin is
created at boot and drifts over time, which is acceptable for local goals but
not for reusable room coordinates. Named locations therefore remain disabled;
use the 3D panel for a short-lived goal. The physical controller uses a
turn-aware progress check and a reduced differential-drive trajectory sample
set so a long initial turn is not mistaken for a stalled robot on the Pi. To
inspect the current local pose:

```bash
ros2 run tf2_ros tf2_echo odom base_link
```

For a future second top camera, make its driver publish
`sensor_msgs/msg/CompressedImage` and pass its topic to the bridge:

```bash
ros2 topic list -t | grep 'sensor_msgs/msg/CompressedImage'
./robot/run_bridge.sh \
  secondary_camera_topic:=/top_camera/image_raw/compressed
```

Real mode never falls back to the fake robot. `--robot-url` is required, while
`--camera-url` selects the Orin OAK-D and, by default, its Kokoro TTS service.
`./app live` remains the lower-level one-turn diagnostic command.

## Safety and current limits

Gemini can request named navigation, bounded Create 3 distance motion without
Nav2 lidar-costmap collision projection, collision-checked Nav2 spins, explicit
dock/undock, speech, and stop. It never receives raw
velocity, motor, map-coordinate, or arbitrary-pose tools. The ROS bridge also
refuses concurrent motions. `Stop robot` cancels both bridge-owned motions and
any active Nav2 pose goal published directly from Lichtblick.

Object approach and person-facing are deliberately rejected on the real bridge
until RGB-depth grounding is implemented. The fake mission exercises those
beats, but the physical robot will currently navigate, look, comment, and stop.
The mission panel's top status pill shows live dock state and battery percentage.

Run `SILLY_CAMERA_URL=http://ORIN_IP:8081 ./robot/smoke.sh` on the Pi to verify
mapless Nav2, scan, odometry, rolling costmap, bridge, and OAK-D without
commanding motion.

## Upstream references

- [TurtleBot 4 Jazzy simulator](https://turtlebot.github.io/turtlebot4-user-manual/software/turtlebot4_simulator.html)
- [TurtleBot 4 navigation](https://turtlebot.github.io/turtlebot4-user-manual/tutorials/navigation.html)
- [TurtleBot 4 OAK-D topic in the simulator bridge](https://github.com/turtlebot/turtlebot4_simulator/blob/jazzy/turtlebot4_gz_bringup/launch/ros_gz_bridge.launch.py)
- [Nav2 Humble `NavigateToPose`](https://api.nav2.org/actions/humble/navigatetopose.html)
- [Gemini Robotics streaming](https://ai.google.dev/gemini-api/docs/robotics-streaming)
- [Kokoro-82M model card](https://huggingface.co/hexgrad/Kokoro-82M)
- [Kokoro ONNX runtime](https://github.com/thewh1teagle/kokoro-onnx)
