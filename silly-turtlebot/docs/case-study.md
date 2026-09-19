---
title: Building a mobile home robot with Gemini Robotics ER 2 and ROS 2 in under an hour
summary: A TurtleBot 4 sends camera and robot state to Gemini Robotics ER 2, while a deterministic guard, ROS 2, and Nav2 stay in charge of motion.
collection: blog
category: tutorial
kind: tutorial
voice: product-lab
author: Robium team
audience: robotics-developer
level: intermediate
tags: [robium, gemini-robotics, turtlebot4, turtlebot3, ros2, nav2, gazebo, oak-d, lichtblick, voice]
app: silly-turtlebot
date: 2026-09-17
tested: 2026-09-14
hero: gazebo-oakd-after.jpg
hero_alt: A simulated TurtleBot 4 camera view inside the furnished Gazebo home
featured: false
---

Who said robots need to be serious?

This project started at Founders Inc's [Silly Robot
Hackathon](https://luma.com/sillybot?tk=0DYbRY) in San Francisco, an evening for
building robots that were whimsical, funny, or simply unnecessary. We wanted a
small home robot that could move between rooms, notice what was happening, make
the occasional joke, and sometimes decide that a request did not deserve
immediate attention.

We used a TurtleBot 4, which combines an iRobot Create 3 mobile base with a
Raspberry Pi and the ROS 2 navigation stack. We had less than an hour for the
first version, and Gemini Robotics ER 2 Streaming had just become available.
Rather than attempt the whole robot at once, we gave ourselves a small target:
one instruction, one camera view, a few safe actions, and something visible at
the end.

The jokes were easy. The hard part was letting Gemini interpret an open-ended
request without quietly turning it into the robot's motor controller. We split
the job in two. Gemini Robotics ER 2 handles language, vision, conversation,
and high-level decisions. ROS 2 and Nav2 handle motion, localization, obstacle
checks, and action completion.

## ER 2 for decisions, ROS 2 for motion

The names are close, but [Gemini Robotics
2](https://deepmind.google/models/gemini-robotics/) and Gemini Robotics ER 2
have different jobs. Gemini Robotics 2 is a vision-language-action model. It
turns camera and language input into motor actions for manipulation and
whole-body control.

Gemini Robotics ER 2 is an embodied-reasoning vision-language model. It watches
video, listens to instructions, plans multi-step work, and calls tools. It then
hands execution to a lower-level VLA or an existing robot API. That fit our
TurtleBot: Nav2 already knew how to plan a route and avoid obstacles, so there
was no reason to replace it with learned motor control.

We used `gemini-robotics-er-2-streaming-preview`. The streaming endpoint keeps
one Live API session open for text, JPEG frames, and raw microphone audio. Its
output is text plus function calls. Speech stays a separate tool, and the model
never sends wheel speeds directly.

## Give Gemini a small set of robot skills

We began with a fake robot and one deterministic mission. This let us test the
Gemini interaction before a physical robot could move:

1. Send an instruction and an optional camera frame or audio clip.
2. Receive model text or a function call.
3. Check the requested action and arguments in ordinary Python.
4. Execute the action through the fake robot.
5. Return the result with the matching call ID.
6. Continue until the model completes the task.

The same guarded interface now runs against a fake robot, two Gazebo profiles,
and the physical TurtleBot. In simulation, Gemini can inspect state, move a
bounded distance, rotate, navigate to a named location, look around, speak,
stop, or complete a task. The real robot exposes only the capabilities its
running bridge reports; named locations are disabled there because the current
hardware setup does not keep a persistent room map. Gemini never gets access
to `/cmd_vel`, arbitrary poses, or unrestricted coordinates.

The guard is a small deterministic layer between Gemini and ROS. It rejects
unknown tools, extra arguments, invalid numbers, overlapping motion, and object
IDs that did not come from current perception. Tool descriptions help the model
choose correctly; Python remains responsible for enforcing the rules.

> [!DECISION]
> Gemini chooses what the robot should try next. Existing robot software decides
> whether the request is valid and owns the final motion command.

## How the parts connect

![Silly TurtleBot system flow](../assets/diagrams/system.svg)

*ER 2 interprets the instruction and camera stream. The guard converts approved
requests into ROS 2 and Nav2 actions, while the browser shows the same robot
state through a separate visualization path.*

The Gemini agent runs in a locked Python environment and talks to a narrow HTTP
adapter. ROS 2 stays on the robot or inside the simulator, where Nav2 owns route
planning, lidar costmaps, odometry, docking, and action cancellation. This keeps
API and network failures away from low-level motion.

For local simulation, ROS 2 Jazzy, Gazebo Harmonic, Nav2, and a simulated camera
run together in Docker. The fast default now uses a TurtleBot3 Waffle Pi. It
has far fewer render-based sensors than TurtleBot 4, so the furnished house can
run close to real time on a CPU while updating the camera more often. A second
profile keeps the full TurtleBot 4 stack for work that needs Create 3 and
hardware parity.

Both profiles use the same house, map, waypoints, guarded robot API, and
Lichtblick layout. Mission Control sits beside the 3D navigation view, camera,
teleoperation pad, and ROS logs, so the operator can watch the model's request
and the robot's response in the same window.

## Keep one mission session open

Our first version opened a new Gemini connection for each instruction. It lost
context between requests and made a moving robot look idle in the browser.

The current app keeps one Gemini session open while the robot is running. A
background worker receives text and tool calls, while a single writer sends
instructions, recent camera frames, and tool results. Only the newest frame is
kept, so a slow connection cannot build a queue of old scenes.

The browser no longer waits for an entire mission before showing anything.
Model text and guarded tool progress arrive as timestamped events. While a
mission is running, the instruction box stays editable and **Run mission**
becomes **Update mission**. **Stop robot** remains available and closes the
current Gemini turn before calling the guarded stop path.

Camera frames update the session but do not start a new reasoning turn by
themselves. We send a short heartbeat only when no model turn or robot action
is waiting to finish. After motion, Gemini receives the final robot state and a
fresh image before deciding what to do next.

## Test the same actions in three places

We kept the progression small:

- A fake adapter tested function calls, validation, cancellation, and session
  behavior without Gemini credits, ROS, or hardware.
- Gazebo tested localization, named goals, bounded movement and rotation,
  camera frames, manual teleoperation, and the browser view in a furnished
  home. The fast TurtleBot3 profile is the everyday path; the TurtleBot 4
  profile remains available when Create 3 behavior matters.
- The physical robot tested the same semantic actions against ROS 2 Humble,
  Nav2, lidar, odometry, docking, OAK-D vision, and bounded speech.

The Gazebo smoke check now requires a healthy bridge, localization, Nav2's
forward, reverse, and spin actions, named locations, a fresh camera frame, and
the browser controls. We still use bounded console missions for the behavior
check: a short move, a rotation, and one open-ended room instruction.

## Run the local demo

You need Git, Docker with Compose v2, a modern browser, and a Gemini API key.
Load the key through your shell or secret manager, then run:

```bash
npx robium-ai@latest setup
git clone https://github.com/robium-ai/robium-apps.git
cd robium-apps/silly-turtlebot
./app doctor
./app run
```

Open [http://localhost:8091](http://localhost:8091), enter a mission, and select
**Run mission**. The default is the faster TurtleBot3 Waffle Pi simulation. It
does not need a physical robot, GPU, or local ROS installation.

Use the TurtleBot 4 profile when you are checking Create 3 behavior or preparing
something that needs to transfer to the physical robot:

```bash
./app run --sim --robot tb4
```

The browser console shows Mission Control on the left, the map and robot in the
center, and the camera and manual drive pad on the right. The drive pad bypasses
Gemini but stays inside its own speed limits, which is handy when you need to
reposition the simulator between missions.

For a hardware-free run without Gemini or Gazebo, use the deterministic mock.
The smoke command adds the guard, session, camera, cancellation, and browser
API tests:

```bash
./app demo
./app smoke
```

The console and simulator run on your machine. This project does not currently
offer a public hosted session; “live” below means the real TurtleBot path.

## From simulation to the TurtleBot

Moving to hardware did not give Gemini a second, lower-level control interface.
The same guard talks to the TurtleBot's native ROS 2 and Nav2 services and
reports which actions are actually available. An OAK-D camera supplies frames,
and a separate speech service handles the `speak` action.

Start the live control plane from the repository and point it at the Raspberry
Pi and Orin services:

```bash
./app run --real \
  --robot-url http://ROBOT_IP:8088 \
  --camera-url http://ORIN_IP:8081
```

This opens the same console at [http://localhost:8091](http://localhost:8091).
The physical setup currently uses rolling Nav2 costmaps in `odom`, not a saved
room map, so named locations are disabled. The operator can still place a
short-lived goal in the 3D view, while Gemini uses the bounded motion, rotation,
speech, state, and stop tools exposed by the live bridge. Navigation can keep
running if vision or speech stops responding.

> [!EVIDENCE]
> The mock mission, Gazebo navigation and camera path, physical ROS/Nav2 state,
> OAK-D capture, browser preview, and bounded speech have passed separately.
> Repeated autonomous physical missions remain a supervised validation step.

## What ER 2 Streaming does not do

The streaming endpoint is still a preview. It accepts text, images, and audio,
but returns text, limits JPEG input to one frame per second, and supports only
blocking function calls for robotics. Google's [streaming
guide](https://ai.google.dev/gemini-api/docs/robotics-streaming) requires a
physical action to finish and return its tool result before the model selects
the next one.

That makes the robot tool loop sequential. We can keep showing local progress
and accepting camera frames while Nav2 is moving, but Gemini waits for the
terminal result before issuing another action. This is a useful constraint for
a small mobile robot, although it limits overlapping work and richer concurrent
control.

Google's [Robotics Live API
examples](https://github.com/google-gemini/robotics-samples/tree/main/live-api)
show the same pattern on other embodiments. The [Spot snack-fetch
example](https://github.com/google-gemini/robotics-samples/tree/main/live-api/spot)
uses ER 2 to coordinate navigation and manipulation APIs rather than replacing
Spot's controllers. We used that same division of responsibility with Nav2.

The under-an-hour build was the first fake-robot loop, not the complete system
described here. Gazebo, the persistent browser session, camera delivery, and
physical hardware checks came afterward. The physical components have passed
separately; repeated end-to-end autonomous missions still require supervised
testing.

## The Robium skills behind the build

[architect](https://github.com/robium-ai/robium/tree/main/skills/architect)
helped us keep the first hackathon version to one visible outcome.
[gemini-robotics](https://github.com/robium-ai/robium/tree/main/skills/gemini-robotics)
covered the persistent streaming session and tool-response loop.
[ros2](https://github.com/robium-ai/robium/tree/main/skills/ros2),
[navigation](https://github.com/robium-ai/robium/tree/main/skills/navigation),
and [integration](https://github.com/robium-ai/robium/tree/main/skills/integration)
kept Gemini above the existing motion stack.

[simulation](https://github.com/robium-ai/robium/tree/main/skills/simulation),
[gazebo](https://github.com/robium-ai/robium/tree/main/skills/gazebo),
[foxglove](https://github.com/robium-ai/robium/tree/main/skills/foxglove), and
[testing](https://github.com/robium-ai/robium/tree/main/skills/testing) helped
us carry the same interface from a fake robot to Docker and then to hardware.

The useful part is not the robot's sense of humor. It is the boundary: Gemini
can interpret a scene and decide what to try, but the robot software still owns
what is allowed and how motion is executed.

Source, tests, deployment scripts, and the architecture brief live in the
[Silly TurtleBot repository](https://github.com/robium-ai/robium-apps/tree/main/silly-turtlebot).
If something does not work, ask in the [Robium Discord](https://robium.ai/join/discord)
or [create an issue](https://github.com/robium-ai/robium-apps/issues/new) with
your operating system, Docker version, and the command output.
