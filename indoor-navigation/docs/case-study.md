---
title: A robot maps a world it has never seen, then drives it
summary: The classical autonomous-navigation pipeline (SLAM, Nav2, Gazebo) built end-to-end by an AI coding agent, running headless in one Docker image with the viewer bundled in.
app: indoor-navigation
date: 2026-08-05
hero: assets/trailer.gif
hero_alt: Simulated TurtleBot 3 driving itself to a clicked goal in the bundled browser viewer (simulation footage)
featured: true
---

# Case study: indoor-navigation

*A TurtleBot 3 explores a world it has never seen, maps it, and then drives
itself to any goal you click — built end-to-end by an AI coding agent using
the Robium skill pack, and runnable by anyone with Docker in two commands.*

## The problem

Classical autonomous navigation is the "hello world" of mobile robotics, but
a surprisingly hostile one to reproduce: it spans a simulator, a SLAM
library, a localization stack, a planner, and a visualization tool, each
with its own configuration dialect, and the reference tutorials assume a
Linux desktop with a display. The goal here was the full pipeline —
SLAM → save the map → localize → plan → drive — running headless on a
GPU-less Apple Silicon laptop, reproducible from a clean clone, with a
one-command pass bar.

## Constraints

- **Host:** macOS on Apple Silicon. No native ROS 2, no display server, no
  NVIDIA GPU. Everything must live in one arm64 Docker image.
- **Honesty:** simulation only, clearly labeled; the pass bar must assert
  real behavior (goals reached), not just processes starting.
- **Reproducibility:** local runs and hosted demo instances must be the
  same artifact.

## The approach

ROS 2 Jazzy + Nav2 + slam_toolbox + Gazebo Harmonic (via ros_gz), TurtleBot 3
Burger, all headless with software rendering. Compose profiles are the
scenarios — `sim`, `slam`, `nav`, `demo`, `test` — and every node of a
scenario runs in ONE container, because DDS multicast does not cross
Docker's bridge network on macOS.

The map is the app's one data artifact: a scripted route drives the robot
while slam_toolbox builds the occupancy grid; `map_saver_cli` commits it;
AMCL localizes on it forever after. Nav goals are map-frame, and the map
origin is the robot's *starting pose*, not the world origin — the kind of
convention that costs an afternoon the first time and nothing once encoded.

The demo experience is deliberately self-contained: the image bakes in the
Lichtblick web viewer (the open-source Foxglove fork), and the in-container
session gateway serves it on the same port as the WebSocket bridge. Open
http://localhost:8765 and the viewer auto-connects with the nav layout
preloaded — no account, no layout import, no installed tools. The hosted
demo at robium.ai/demos/nav-trial runs the byte-identical container behind
a lifecycle orchestrator; the page simply iframes the viewer the instance
serves itself.

## Robium components used

The architect skill's navigation golden path chose the stack (`ros2` +
`nav2` + `gazebo` + `visualization`), with the environments skill's macOS
rules forcing Docker and the headless-rendering approach. The testing skill
set the shape of the pass bar; the live-demo skill's session contract became
the gateway. The architecture brief was written by the robium-architect
agent at kickoff and is committed next to this file.

## Major decisions

1. **Launch Nav2 servers directly** instead of including nav2_bringup:
   Jazzy's `slam:=True` starts a duplicate slam_toolbox, the stock launch
   hard-codes lifecycle params so `bond_timeout` can't be set (Docker stall
   spikes then kill the stack), and TB3's param substitutions need
   `ParameterFile(allow_substs=True)`.
2. **TwistStamped everywhere:** TB3's Jazzy Gazebo integration ignores
   plain Twist; `enable_stamped_cmd_vel: true` in all five cmd_vel-publishing
   sections.
3. **One container per scenario** (the macOS DDS constraint above) — the
   single most load-bearing environment decision.
4. **Bundle the viewer** rather than deep-linking to a hosted viewer app:
   it turned a login wall plus a manual layout import into "open a URL",
   and made the local and hosted flavors the same demo.
5. **A session gateway in front of the bridge:** first WebSocket claims the
   instance, intruders get 409/403, `/status` streams the boot log, and
   `/shutdown` SIGINTs PID 1 (SIGTERM to PID 1 is ignored by the kernel
   when unhandled). Extracted later as the vendorable
   shared/demo-gateway package.

## Results

- `make smoke`: full stack boots headless, two map-frame goals return
  `SUCCEEDED`, ~90 s warm, exit-code chain through make. RTF ≈ 1.0 in
  Docker-on-macOS with software rendering — essentially real time without
  a GPU.
- `make demo` + a browser is the complete local experience; the same image
  serves per-visitor instances on Cloud Run/orchestrator infrastructure
  with scale-to-zero.
- The quickstart is verified as written: a clean copy outside the repo ran
  `make build && make demo`, the viewer auto-connected, and a clicked goal
  drove the robot (2026-08-03).

## Limitations

- Simulation only; no sim-to-real path is claimed.
- The lidar renders through llvmpipe: fine for a 360-sample TB3 scan,
  not a template for camera-heavy sensors.
- Pinned to ROS 2 Jazzy; Nav2's next major line will make a distro bump a
  real migration, accepted knowingly.
- On multicast-less hosts (Cloud Run), gz-transport discovery loses a
  sticky per-boot race roughly half the time; an in-container watchdog
  restarts the instance rather than pretending it can be prevented.

## Next steps

Promotion to the public robium-apps showcase; re-vendoring the gateway from
shared/demo-gateway at the next touch; and using this app as the bootstrap
base (`robium-ai app new <id> --from indoor-navigation`) for the next
ROS 2 + Nav2-class application.
