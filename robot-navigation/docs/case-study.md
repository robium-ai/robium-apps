---
title: Mapping and navigation with ROS 2, from one app
summary: Drive a simulated TurtleBot3, build a map, localize, save waypoints, and watch Nav2 plan in a browser workspace.
collection: blog
category: tutorial
kind: tutorial
voice: product-lab
author: Robium team
audience: robotics-developer
level: intermediate
app: robot-navigation
date: 2026-08-28
tested: 2026-08-16
tags: [robium, ros2, nav2, gazebo, slam, turtlebot3, visualization, lichtblick, foxglove]
hero: assets/gifs/trailer.gif
hero_alt: A simulated TurtleBot3 follows a planned route through a mapped environment
social_image: assets/social/card.png
featured: true
---

A navigation goal looks like one click in the browser. Behind it, localization
has to agree with the map, the planner has to find a route, the controller has
to turn that route into velocity commands, and the simulated sensors have to
keep the robot out of walls.

This application puts that full loop in one place. A TurtleBot3 Waffle Pi runs
in Gazebo, SLAM Toolbox builds the map, AMCL localizes against it, Nav2 drives
the robot, and Lichtblick shows the camera, plans, transforms, logs, and
application controls.

![A TurtleBot3 mapping and navigating in the browser workspace](../assets/gifs/trailer.gif)

*A recorded Gazebo session viewed through Lichtblick. The robot, occupancy map,
active plan, camera, and control panel update from the same ROS 2 system.*

## One loop, two environments

The application includes a simulated house and an industrial warehouse. Both
use the same workflow:

1. Start the simulation.
2. Drive while SLAM builds an occupancy map.
3. Save the map and load it for localization.
4. Give AMCL an initial pose.
5. Send a goal or save the current pose as a waypoint.
6. Watch Nav2 plan, control, and report status.

The browser workspace uses
[Lichtblick](https://github.com/Lichtblick-Suite/lichtblick) with a committed
layout and the reusable Robium Dashboard extension. The same ROS data is also
available to the official [Foxglove](https://docs.foxglove.dev/) application at
`ws://localhost:8765`.

Lichtblick is the default because it can ship with the application and does not
require an account. Foxglove remains useful for teams that want its broader
product and support.

## How the pieces connect

![Robot Navigation system flow](../assets/diagrams/system.svg)

*Gazebo publishes the simulated sensors and motion. ROS 2 navigation processes
consume that data, then the bridge and application services expose it to the
browser.*

The main ROS processes share one container and network namespace. On Docker
Desktop for macOS, this avoids DDS multicast discovery problems between
containers. It also gives local and hosted runs one portable image.

Gazebo publishes lidar, odometry, IMU, camera, and transforms. During mapping,
`slam_toolbox` turns lidar and odometry into an occupancy map. During
localization, AMCL estimates the robot pose on a saved map. Nav2 plans a route
and publishes velocity commands. `foxglove_bridge` carries the topics and
services to the browser.

The Dashboard stays separate from the app-specific ROS interfaces. Another
project can reuse the extension with fewer controls, different service names,
or no simulator section.

## Start the stack

You need Git, Docker with Compose v2, a modern browser, and ports 8080 and 8765.
The simulation does not require a GPU, physical robot, or system ROS install.

```bash
npx robium-ai@latest setup
git clone https://github.com/robium-ai/robium-apps.git
cd robium-apps/robot-navigation
./app doctor
./app run
```

Open [http://localhost:8080](http://localhost:8080). The robot and Gazebo start
in the background, but the application begins in `IDLE`. Mapping and
localization start only when requested.

The first image build can take about ten minutes. Later runs reuse it unless
the source, dependencies, Dashboard, or simulation assets change. The
[application README](https://github.com/robium-ai/robium-apps/tree/main/robot-navigation)
covers remote access, remaining commands, and troubleshooting.

## Build a map that localization can use

Choose House or Warehouse, enter a map name, and select Start mapping. Drive
with WASD, arrow keys, or the on-screen controls. The lidar scan appears in the
3D view while `slam_toolbox` expands the occupancy map.

![The occupancy map growing as TurtleBot3 explores the house](../assets/gifs/mapping.gif)

*The camera, scan, occupancy map, logs, and Dashboard stay visible during the
mapping run.*

Observe walls from more than one angle and return near the starting area to
close the loop. A quick pass can leave gaps or misaligned walls even when the
map looks mostly filled.

Finish mapping saves the files for the active environment and returns the app
to `IDLE`. Maps and waypoint sidecars remain local and untracked.

## Localize before tuning the planner

Load the saved map, then set the robot's initial pose and heading in the 3D
panel. Before sending a goal, check that the map is visible, the scan aligns
with nearby walls, and the robot model sits where expected.

If the scan is offset, fix the initial pose first. Planner tuning cannot
compensate for a robot localized in the wrong place.

> [!DECISION]
> The workspace keeps localization, plans, and logs visible together because a
> missing route and a bad pose can look like the same “robot does not move”
> failure from a control panel alone.

## Follow a route and save the destination

Use the 3D goal tool to select a reachable point and heading. Nav2 draws the
global plan in cyan. The local controller plan appears in orange and adjusts as
the robot moves.

![Nav2 global route over the saved occupancy map](../assets/stills/navigation-plan.png)

*The saved map, localized robot pose, and active global route are visible
before the robot starts moving.*

A waypoint stores the robot's current map-frame position and heading. Drive or
navigate to a useful place, give it a name, and select Save position. Waypoints
are stored per map in `<map>.waypoints.json`, so locations from one environment
do not appear in another.

![Named waypoints in the Robium Dashboard](../assets/stills/waypoint-saved.png)

*Bedroom, dining table, and kitchen remain attached to the selected house map.*

Stop navigation cancels the active Nav2 goal. Stop robot also publishes zero
velocity. In this simulated application it is a useful control, not a hardware
emergency stop.

## Read the visible layers before the logs

The map and plan displays narrow failures quickly:

- No map usually points to the session or map server.
- No global plan points to localization, the goal, or the planner.
- A global plan with no motion points farther down the command path.
- A changing local plan with repeated stops often points to sensors, costmaps,
  or collision monitoring.

The log panel then filters the shared `/rosout` stream into all messages,
navigation, and mapping plus application output. A plan only exists after Nav2
receives a goal, so an empty plan display is not automatically an error.

> [!EVIDENCE]
> The recorded sessions cover mapping, map reuse, initial-pose correction,
> waypoint storage, and multiple navigation goals in Gazebo. They do not cover
> a physical TurtleBot3.

## Debug the path, then keep the lesson

The `architect`, `simulation`, and `visualization` skills kept the first slice
on one inspectable navigation loop. `integration` and `environments` shaped the
single-container ROS boundary. `ros2`, `nav2`, and `foxglove` guided the topic,
transform, localization, and browser interfaces.

The repeated lesson was to debug the visible data path before changing
parameters. Fixes for browser publishers, velocity message types, map sessions,
simulation assets, and waypoint storage were added back to the relevant skills
rather than staying as notes inside this app.

## Simulation is the boundary

This project covers one simulated TurtleBot3 model with two Gazebo
environments. Connecting the same surface to a physical robot needs separate
hardware interfaces, networking, safety controls, and calibration. The bundled
Lichtblick layout is the primary browser experience; Foxglove can inspect the
ROS data but does not receive the same configured Dashboard workflow.

Source, smoke tests, architecture notes, and the reusable Dashboard live in the
[Robot Navigation application](https://github.com/robium-ai/robium-apps/tree/main/robot-navigation).
