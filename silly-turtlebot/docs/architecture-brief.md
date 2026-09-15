# Architecture Brief: Silly TurtleBot

**Date:** 2026-09-09
**Status:** active

## Goal and constraints

Build a TurtleBot 4 agent that can understand open-ended navigation requests,
move with Nav2, and continuously reason over an OAK-D camera stream plus live
robot state.

The first slice proved the Gemini Robotics ER 2 Streaming session shape,
bounded tool contract, and deterministic navigation mission against a fake
TurtleBot. The second slice adds a robot-side ROS 2 bridge for named Nav2 goals,
bounded distance motion and collision-checked spins, OAK-D/top-camera JPEG
frames, cancellation, and TTS.
The third slice adds a reproducible TurtleBot 4 Gazebo Harmonic runtime in the
same furnished home and map used by `robot-navigation`. The simulation now
passes a fresh-container smoke covering all three Nav2 actions and a fresh OAK-D
JPEG, plus real forward and quarter-turn actions through Nav2. The physical
slice now runs mapless, odom-relative Nav2 on the Pi, DepthAI capture on the Orin, and the
Gemini/Lichtblick control plane on the operator host.

Provisional hardware target: the existing TurtleBot 4 running Ubuntu 22.04 and
ROS 2 Humble from `robot-teleoperation`. If the robot has been upgraded to the
current Jazzy image, the ROS overlay will match Jazzy instead; the agent/tool
contract does not change.

## Decisions

| Decision | Choice | Why now | Confidence |
| --- | --- | --- | --- |
| First working slice | Spoken/text mission shape, optional JPEG/raw PCM input, fake semantic robot tools, and one deterministic navigation routine | Exercises the unfamiliar ER 2 streaming boundary without risking physical motion | validated locally including one live ER 2 tool-call turn |
| Embodied model | `gemini-robotics-er-2-streaming-preview` | It accepts audio, images, and text in one persistent session and supports blocking function calls | live OAK-D-to-speech turn succeeded |
| Motion authority | Nav2 plus Create 3 actions behind a mission guard; Gemini never receives `/cmd_vel` or unchecked coordinates | Keeps bounded distance, speed, and concurrency enforcement in the deterministic robot layer while allowing deliberate close approach without lidar-costmap projection | validated architecture |
| Speech output | A bounded `speak(message)` tool backed by Kokoro-82M ONNX on the Orin, with Pi `espeak-ng` retained only as a no-Orin fallback | Neural speech is smoother, and its separate HTTP/container boundary cannot disturb Nav2 or camera capture | ARM64 deployment, model inference, USB discovery, and clear audible output passed on hardware |
| Agent environment | Locked uv package in a small Docker image | Keeps the cloud client reproducible and independent from the Pi's ROS Python | deployed on the operator host |
| ROS environment | Native Humble TurtleBot underlay plus an app overlay on the Pi | Reuses stock hardware drivers and keeps all DDS/Nav2 traffic on one host | deployed; actions, scan, odom, rolling costmaps and lifecycle verified |
| Simulation | ROS 2 Jazzy + Gazebo Harmonic + official TurtleBot 4 simulator in one Docker container | Jazzy/Harmonic is the supported current pairing; one container avoids Docker Desktop DDS discovery failures | fresh-container smoke passed; Nav2 forward and spin actions succeeded |
| Simulation world | Pinned AWS RoboMaker Small House asset and matching map/waypoints reused from `robot-navigation` | Gives scene commentary and navigation a furnished, repeatable environment without a second unverified map | TurtleBot 4, localization, Nav2, and OAK-D stream validated together |
| Agent-to-robot boundary | Narrow HTTP bridge on the robot LAN; native ROS 2 actions/topics behind it | Separates cloud/API failure from motion and avoids cross-host DDS | deployed and healthy; SSH/tunnel remains appropriate off-LAN |
| Cameras | OAK-D via pinned DepthAI 2.33 container on Orin; direct full-frame HTTP for Gemini plus a Pi-side 1 FPS compressed-image ROS relay and a 16-message Foxglove live-view backlog for Lichtblick | Keeps vision/Gemini compute on Orin while exposing the low-bandwidth preview through the regular Image panel; stale frames are dropped after a client/network stall | fresh 640×360 Gemini JPEG and 320×180 operator preview verified end-to-end |
| Neural TTS | Separate Kokoro-82M v1.0 int8 ONNX container on Orin; `am_puck` voice; ALSA USB auto-selection | Keeps model inference off the navigation Pi and isolates camera/TTS failure domains | hot-plugged USB speaker resolved as `plughw:2,0`; speech completed and was confirmed clear |
| Manual motion | Native Lichtblick Teleop panel plus an Orin-paired Stadia forwarder into TurtleBot 4's boot-persistent `teleop_twist_joy` stack | The Orin radio completes the Stadia BLE handshake that this Pi drops; direct Ethernet plus Wi-Fi fallback and a 350 ms Pi watchdog preserve the stock `/joy` contract and fail to neutral | end-to-end `/dev/input/js0` → dual-destination UDP → `/joy` verified over Wi-Fi; app mapper adds A=undock and B=dock without replacing the drive mapping |
| Physical navigation mode | Nav2 in `odom` with 3 m local and 8 m rolling global lidar costmaps; no SLAM, AMCL, or static layer | Enables short collision-checked pose goals immediately, accepting odometry drift instead of requiring a map | active; persistent named waypoints intentionally disabled |
| Agent behavior | Proactive visual navigation with terse progress acknowledgement | Matches the Robotics ER spatial-temporal loop without unrelated character context | implemented locally; robot smoke pending |

## Module boundaries and communications

| Module | Responsibility | Boundary rationale |
| --- | --- | --- |
| `live_agent` | Gemini Live session, multimodal input, text output, and function-call receive loop | Network/API failure domain |
| `mission_guard` | Tool allowlist, argument validation, named locations, stand-off limits, event log | Motion authority must remain enforceable if the model misbehaves |
| `fake_robot` | Hardware-free implementation and deterministic navigation fixture | Enables unit and smoke tests without ROS, a robot, or API spend |
| `rest_robot` | Operator-side semantic HTTP client and camera-frame handoff to Gemini | Keeps ROS imports out of the uv agent and makes network failures explicit |
| `silly_turtlebot_ros` | Nav2/Create 3 actions, battery and camera subscriptions, health, goal cancellation, fallback TTS, and an isolated HTTP-to-ROS OAK-D preview relay | ROS-specific processes on the robot; native actions/topics internally, with camera I/O separated from navigation callbacks |
| `gamepad_actions` | Convert rising edges from spare `/joy` face buttons into Dock/Undock actions; ignore them while a drive shoulder is held | Extends TurtleBot 4's existing boot-time joystick stack without duplicating its motion publisher |
| `remote_joy` + `orin/gamepad_sender` | Forward the Orin's hot-pluggable Linux joystick over dedicated `10.42.0.0/30` Ethernet and Wi-Fi fallback to a source-restricted Pi UDP receiver that publishes `/joy` and stops on timeout | Avoids unsafe cross-host DDS changes, survives loss of either local path, and retains TurtleBot's stock teleop mapping and automatic boot behavior |
| `orin/tts_server` | Load Kokoro once, serialize short speech requests, and play WAV through ALSA | Model and audio failures restart independently from OAK-D and navigation |
| `silly_turtlebot_sim` | Modern-Gazebo world repair, official TurtleBot 4 spawn/bridges, localization, Nav2, and camera compression | Simulation-only composition; preserves the physical robot's semantic HTTP contract |

Gemini calls only these semantic operations:

- `get_robot_state()`
- `move_distance(distance_m, speed_mps)` (signed 0.10–2.00 m)
- `rotate_by(angle_deg)` (signed 1–180 degrees)
- `move_for_duration(linear_mps, angular_rad_s, duration_s)` through Nav2
  AssistedTeleop
- `navigate_to_location(location)`
- `move_forward(distance_m)` (0.10–1.00 m, fixed bridge speed)
- `look_around(quarter_turns)`
- `approach_object(object_id, stand_off_m)`
- `face_nearest_person()`
- `speak(message)`
- `stop(reason)`
- `ack(status)` and `complete_task(summary)` (agent-loop control only)

There is deliberately no motor, wheel, pose, or arbitrary-coordinate tool. The
bounded velocity-duration tool is mediated by Nav2 AssistedTeleop. Every Live
API tool is blocking.

## Provisional assumptions and risks

| Assumption or risk | Impact | Cheapest validation | Authorized pivot |
| --- | --- | --- | --- |
| ER 2 preview access and current SDK surface work with the maintainer's restricted API key | Blocks the live agent, not the mock demo | Run one text + JPEG tool-call session with the fake robot | Adapt to the current SDK or use standard ER 2 snapshot calls while retaining the guard |
| Python 3.10 lock resolves on Raspberry Pi arm64 | Blocks robot-side agent install | `uv sync --locked` on the robot | Run the agent on an offboard Linux host and keep the ROS bridge on the robot |
| Existing robot is still Humble | Changes package names and launch details | Read `/etc/os-release`, `$ROS_DISTRO`, and installed TurtleBot packages | Match the installed Jazzy image instead; do not upgrade as part of this app |
| OAK-D RGB/depth can ground a floor object into `map` with useful accuracy | Blocks exact object approach, not relative navigation | Detect one staged object, project median depth, and compare against a measured floor position | Stop at a safe distance and continue with camera-relative motion only |
| Contest network sustains the cloud session | Affects responsiveness | Timed rehearsal on the actual hotspot/network | Cache the staged routine and fall back to local triggers and prerecorded lines |

## Implementation path

1. Build the uv package, fake mission guard, deterministic navigation routine, and
   ER 2 Streaming adapter for text, JPEG, and raw 16 kHz PCM input.
2. Keep ten critical tests and `./app smoke` hardware-free.
3. Run one live session where ER 2 calls only guarded fake tools.
4. Deploy the ROS 2 overlay and pass `robot/smoke.sh` against the physical
   Humble TurtleBot 4; validate short odom goals under supervision.
5. Pass `./app sim-smoke` and a Nav2 motion command in the furnished home.
   Rehearse a full Gemini navigation turn with an open-ended spatial prompt.
6. Add RGB-depth object/person grounding, then pass the staged object mission
   three consecutive times under human supervision.

## Robium skill feedback

This app is the concrete use case requested by
[`robium#25`](https://github.com/robium-ai/robium/issues/25): it names Gemini
Robotics ER 2 Streaming, exercises multimodal input plus blocking function
calls, and validates the model behind a guarded ROS/Nav2 boundary. Any follow-up
Robium guidance should therefore be a focused Gemini Robotics integration skill
covering the verified SDK/session behavior and robot-safety boundary. It should
not become a broad vendor catalog or duplicate the existing ROS 2 and Nav2
skills. The fake adapter, one live tool-call turn, Gazebo runtime, and eventual
physical-robot smoke provide progressively stronger validation fixtures for
that skill.

## First-slice pass bar

- `./app demo` visibly labels the run as mocked and completes the same semantic
  sequence expected on hardware.
- Unknown waypoints, arbitrary tools, excessive turn counts, unsafe stand-off
  distances, and overlong speech are rejected before reaching an adapter.
- `./app smoke` passes from the worktree with no robot, no API key, and no
  network request.
- The robot slice requires `/navigate_to_pose`, `/drive_distance`, `/spin`,
  scan, odometry, an odom-frame rolling costmap, and a fresh Orin OAK-D JPEG to pass `robot/smoke.sh` on
  hardware. This smoke passes and does not command motion.
- The simulation slice is not accepted until `./app sim-smoke` observes both
  Nav2 actions and a fresh simulated OAK-D JPEG through the semantic bridge.
