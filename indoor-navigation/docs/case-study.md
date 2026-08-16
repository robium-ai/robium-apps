---
title: Build an indoor navigation app with ROS 2, Nav2, and Gazebo
summary: Map a simulated home, save robot waypoints, and send navigation goals from a browser dashboard.
collection: blog
category: tutorial
kind: tutorial
voice: technical
author: Robium team
audience: robotics-developer
level: intermediate
app: indoor-navigation
date: 2026-08-15
tested: 2026-08-14
tags: [ros2, nav2, gazebo, slam, visualization]
hero: assets/trailer.gif
hero_alt: Simulated TurtleBot3 Waffle Pi navigating through an indoor environment in the browser dashboard
featured: true
---

A TurtleBot3 drives through a simulated home while its lidar fills in an
occupancy map. When the map is ready, the same browser panel can load it, save
the robot's current position as a waypoint, and ask Nav2 to drive back there.

This tutorial runs that complete workflow on a laptop. Gazebo simulates the
robot and environment. ROS 2 carries sensor data and commands. `slam_toolbox`
builds the map, Nav2 handles localization and navigation, and Lichtblick shows
the camera, map, plans, and logs.

The project is simulation-only today. You do not need a physical robot, GPU,
or system ROS installation.

## What you will run

The application provides one interactive control panel for the main indoor
navigation loop:

1. Start a TurtleBot3 Waffle Pi in the House or Warehouse environment.
2. Drive the robot while SLAM builds a map.
3. Save the map and load it for localization.
4. Save the current robot pose as a named waypoint.
5. Send a goal and watch Nav2 plan and drive.

The default layout keeps the working views together. The camera and 3D scene
share the top row, ROS logs sit below them, and the Robium Dashboard occupies
the right side.

## Prerequisites

You need:

- Docker Desktop or another Docker environment with Compose v2
- A modern browser
- The [Robium applications repository](https://github.com/robium-ai/robium-apps)

Apple Silicon and other arm64 hosts are supported. The container includes ROS
2 Jazzy, Gazebo Harmonic, Nav2, the browser viewer, and the application code.

## Start the application

Clone the repository, enter the app directory, and check the local setup:

```bash
git clone https://github.com/robium-ai/robium-apps.git
cd robium-apps/indoor-navigation
make doctor
```

`make doctor` checks Docker, Compose, ports 8080 and 8765, and whether the
application image already exists. It does not change the running system.

Build the image once, then start the interactive app:

```bash
make build
make run
```

The first build can take about 10 minutes. Later runs reuse the image unless
the source, dependencies, Dashboard, or simulation assets changed.

Open [http://localhost:8080](http://localhost:8080). The robot and Gazebo are
already running, but the session starts in **IDLE**. There is no `/map` yet.
Mapping and localization start only when you ask for them.

## Create a map

The Simulation section offers two environments:

- **House** is the default and uses the AWS RoboMaker Small House.
- **Warehouse** uses the Open Robotics Tugbot Warehouse environment.

Choose an environment, enter a map name, and select **Start mapping**. The
button changes to **Finish mapping** while the mapping session is active.

Drive the robot with WASD, the arrow keys, or the movement buttons. The lidar
scan appears in the 3D view and `slam_toolbox` updates the occupancy map as new
space becomes visible. Use the speed sliders when narrow passages need slower
motion.

Try to observe walls from more than one angle and close the loop by returning
near the starting area. A map built from one quick pass can look complete while
still containing poor alignments or unexplored gaps.

Select **Finish mapping** when the useful area is covered. The app saves the
map under the selected environment, stops the mapping stack, and returns to
IDLE. Only maps created for the active environment appear in the list.

Saved maps are local files. They are deliberately untracked, and the app does
not delete or publish them automatically.

## Load the map and localize

Select the saved map and choose **Load & localize**. This starts the map server,
AMCL, and Nav2 against that map.

AMCL needs an estimate of the robot's pose within the saved map. Use the 3D
panel's initial-pose tool if the estimate is missing or incorrect. Set the
position first, then drag the heading indicator in the direction the robot is
facing.

Before sending a goal, check three things in the 3D view:

- the map is visible;
- the laser scan lines up with nearby walls;
- the robot model sits where you expect it on the map.

If the scan is offset from the walls, correct the initial pose before changing
Nav2 parameters. A planner cannot compensate for a robot localized in the
wrong place.

## Send a navigation goal

Use the 3D panel's goal tool to select a reachable point and heading. Nav2
creates a global route across the saved map, then the local controller adjusts
that route around nearby obstacles while driving.

The layout uses different colors for the two plans:

- cyan for the global Nav2 plan;
- orange for the local controller plan.

The Navigation card reports **Navigating** while a goal is active. Select
**Stop navigation** to cancel it. The button remains disabled while no goal is
running.

**Stop robot** publishes a zero velocity command and cancels active navigation.
It is useful during simulation, but it is not a hardware emergency stop.

## Save and reuse waypoints

A waypoint records the robot's current map-frame position and heading. It does
not record a point clicked elsewhere in the 3D view.

With a map loaded and localization active:

1. Drive or navigate the robot to the position you want to save.
2. Enter a waypoint name.
3. Select **Save position**.
4. Select **Navigate** beside that waypoint to return to it later.

Waypoints are listed alphabetically and can be deleted from the same card.
They are stored per map in a local `<map>.waypoints.json` sidecar, so a kitchen
waypoint from one map will not appear when another map is loaded.

The Navigate action confirms that Nav2 received the stored pose. Watch the
Navigation status and robot motion to confirm the run itself.

## Use the logs and plans together

The bottom panel provides three views of the shared `/rosout` stream:

- **All** for the complete log;
- **Navigation** for Nav2 and localization nodes;
- **Mapping & App** for SLAM and application services.

If the robot does not move, the visible layers help narrow the problem:

- no map usually points to the session or map server;
- no global plan points to localization, the goal, or the planner;
- a global plan with no motion points farther down the command path;
- a changing local plan with repeated stops often points to sensors, costmaps,
  or collision monitoring.

The 3D visibility settings are stored in the Lichtblick layout. If a plan is
missing, confirm its topic is visible before treating it as a Nav2 failure. A
plan also exists only after Nav2 receives a goal and publishes one.

## What is running underneath

The application keeps the data path conventional:

```text
Gazebo sensors and motion
          |
          v
ROS 2 + slam_toolbox + Nav2
          |
          v
foxglove_bridge + app services
          |
          v
Lichtblick + Robium Dashboard
```

Gazebo publishes lidar, odometry, IMU, camera, and transform data for the
TurtleBot3 Waffle Pi. During mapping, `slam_toolbox` turns lidar and odometry
into an occupancy map. During localization, AMCL estimates the robot pose on a
saved map. Nav2 plans a route and publishes velocity commands. The bridge makes
ROS topics and services available to the browser.

The main workflow keeps these ROS processes in one container and network
namespace. This avoids DDS multicast discovery problems across Docker
containers on macOS. It also gives the project one portable image for local and
hosted runs.

The Dashboard is a reusable Lichtblick extension rather than app-specific
HTML. This app enables mapping, navigation, waypoints, simulation, movement,
and stop controls through its committed layout. Another application can use
the same extension with a smaller set of sections and different ROS interface
names.

## Three lessons from the integration

The interactive workflow hides a fair amount of plumbing. These three checks
were more useful during development than immediately tuning the planner.

### A visible path does not prove the robot can move

Nav2 can accept a goal and draw a valid plan even when its velocity publisher
does not connect to the simulated robot. Inspect both ends of the command topic
inside the ROS environment:

```bash
ros2 topic info -v /cmd_vel
```

The output shows publisher and subscriber message types and QoS settings. In
this application, the Gazebo integration expects
`geometry_msgs/msg/TwistStamped`. The Nav2 components that publish velocity
commands therefore use:

```yaml
enable_stamped_cmd_vel: true
```

A topic name by itself is not a contract. The type and QoS must also match.

### Sensor timing needs margin

The simulated lidar publishes at about 5 Hz, or one scan every 0.2 seconds. A
collision-monitor timeout set to the same 0.2 seconds treated ordinary timing
variation as stale data and stopped the robot. This application uses:

```yaml
source_timeout: 1.0
```

That value belongs to this simulation. The reusable rule is to measure the
sensor period and leave real margin in freshness checks.

### World coordinates are not map coordinates

Gazebo places the robot in a simulation world frame. SLAM creates a map frame
from the robot's mapping start pose. A location copied from Gazebo is therefore
not automatically a valid Nav2 goal.

For one of the project's mapping runs, the Gazebo start pose `(-2.0, -0.5)`
became `(0.0, 0.0)` in the saved map:

```text
map_x = world_x + 2.0
map_y = world_y + 0.5
```

Goals selected in the 3D map already use the map frame. Scripts that begin
with world coordinates must perform the conversion explicitly.

## Stop and inspect the app

Press Ctrl-C in the `make run` terminal, or stop the services from another
terminal:

```bash
make stop
```

Useful lifecycle commands include:

```bash
make status
make logs
make help
```

`make help` also prints the equivalent `robium app` commands.

The source is available in the
[indoor-navigation application](https://github.com/robium-ai/robium-apps/tree/main/indoor-navigation).
The repository also contains the full
[architecture brief](https://github.com/robium-ai/robium-apps/blob/main/indoor-navigation/docs/architecture-brief.md)
and the reusable
[Robium Dashboard](https://github.com/robium-ai/robium-apps/tree/main/shared/lichtblick-dashboard).

This project currently proves the workflow in simulation with one TurtleBot3
Waffle Pi. Connecting the same control surface to a physical robot will require
separate work on hardware interfaces, networking, safety, and configuration.
