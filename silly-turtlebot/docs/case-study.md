---
title: Building a mobile home robot with Gemini Robotics ER 2 and ROS 2 in under an hour
summary: Use ER 2 for visual reasoning, continuous perception, and voice commands while ROS 2 and Nav2 handle proven navigation and control.
collection: blog
category: tutorial
kind: tutorial
voice: product-lab
author: Robium team
audience: robotics-developer
level: intermediate
tags: [robium, gemini-robotics, turtlebot4, ros2, nav2, gazebo, oak-d, lichtblick, voice]
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
first version and wanted to try the newly available Gemini Robotics ER 2
Streaming model. The shortest useful version was one instruction, one camera
view, a few safe actions, and a visible result.

The personality was the easy part. The useful engineering question was how to
let Gemini understand an open-ended request without making it the robot's motor
controller. Our answer was to split the work: Gemini Robotics ER 2 handles
language, vision, conversation, and high-level decisions; ROS 2 and Nav2 handle
motion, localization, obstacle checks, and action completion.

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

The same loop now runs against Gazebo and the real TurtleBot. Gemini can inspect
state, move a bounded distance, rotate, navigate to a named location, look
around, face a person, speak, stop, or complete a task. It cannot use
`/cmd_vel`, send arbitrary poses, or choose unrestricted coordinates.

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

For simulation, ROS 2 Jazzy, Gazebo Harmonic, TurtleBot 4, Nav2, and a simulated
OAK-D camera run together in Docker. The browser uses Lichtblick to show the
camera, map, laser scan, plans, controls, and logs.

## Keep one mission session open

Our first version opened a new Gemini connection for each instruction. It lost
context between requests and made a moving robot look idle in the browser.

The current app keeps one Gemini session open while the robot is running. A
background worker receives text and tool calls, while a single writer sends
instructions, recent camera frames, and tool results. Only the newest frame is
kept, so a slow viewer cannot build a queue of old scenes.

Camera frames update the session but do not start a new reasoning turn by
themselves. We send a short heartbeat only when no model turn or robot action
is waiting to finish. After motion, Gemini receives the final robot state and a
fresh image before deciding what to do next.

## Test the same actions in three places

We kept the progression small:

- A fake adapter tested function calls, validation, cancellation, and session
  behavior without Gemini credits, ROS, or hardware.
- Gazebo tested TurtleBot 4 navigation, localization, camera frames, and the
  browser view in a furnished home.
- The physical robot tested the same semantic actions against ROS 2 Humble,
  Nav2, lidar, odometry, docking, OAK-D vision, and bounded speech.

The Gazebo path was accepted only when a fresh container could start the world,
activate Nav2, return a current camera frame, and complete a short forward move
and quarter turn through the same interface used by Gemini.

## Run it locally

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
**Run mission**. The default path is the Gazebo simulation, so it does not need
a physical robot or a local ROS installation.

For a hardware-free check without Gemini or Gazebo:

```bash
./app smoke
```

The smoke suite covers the action guard, Live API tool loop, persistent
session, heartbeat filtering, camera handoff, cancellation, event replay, and a
deterministic mock mission.

## From simulation to the TurtleBot

Moving to hardware did not change Gemini's tools. The HTTP adapter connected
those same actions to the TurtleBot's native ROS 2 and Nav2 services. An OAK-D
camera supplied frames, and a separate speech service handled the `speak`
action. Navigation could continue if vision or speech stopped responding.

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

`architect` kept the first version focused on one visible outcome.
`gemini-robotics` captured the streaming session and function-response loop.
`ros2`, `navigation`, and `integration` kept Gemini above the existing motion
stack. `simulation`, `gazebo`, `foxglove`, and `testing` shaped the Docker
simulation, browser view, and fake-to-hardware test ladder.

The reusable result is not the robot's sense of humor. It is a compact pattern
for combining high-level visual reasoning with robot software that already
knows how to move.

Source, tests, deployment scripts, and the architecture brief live in the
[Silly TurtleBot application](https://github.com/robium-ai/robium-apps/tree/main/silly-turtlebot).
