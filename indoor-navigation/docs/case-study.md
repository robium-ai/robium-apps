---
title: What it took to make Nav2 reliable in Docker on a Mac
summary: Four integration failures we found while building a repeatable SLAM-to-navigation loop with ROS 2 Jazzy, Gazebo Harmonic, and TurtleBot 3.
kind: engineering-story
voice: team
author: Robium team
audience: robotics-developer
level: intermediate
app: indoor-navigation
date: 2026-08-06
tested: 2026-08-03
tags: [ros2, nav2, gazebo, slam, docker]
hero: assets/trailer.gif
hero_alt: Simulated TurtleBot 3 driving to a selected goal in the browser viewer (simulation footage)
featured: true
---

The first version of this application looked healthy. Gazebo was running,
the browser showed a map and a laser scan, and Nav2 could draw a path to a
goal. The robot did not move.

That gap became the useful part of the project. We were building a small,
reproducible navigation application: map a simulated indoor world, save the
map, restart with localization, and send the robot to known positions. The
software was familiar—ROS 2 Jazzy, Gazebo Harmonic, `slam_toolbox`, AMCL,
and Nav2—but several boundaries between those pieces were easy to get almost
right.

We ended up changing how SLAM was launched, how Nav2's lifecycle was managed,
which velocity message reached Gazebo, and how scripted goals were expressed.
None of the fixes involved tuning the planner.

This is an account of those failures and the checks that now define whether
the application works.

## The result we chose to test

The application runs on Apple Silicon in Docker Desktop, without an NVIDIA
GPU or a native ROS installation. Gazebo renders headlessly through Mesa, and
a bundled [Lichtblick](https://github.com/lichtblick-suite/lichtblick) viewer
shows the ROS data in a browser.

There are two related workflows:

1. The SLAM workflow drives a fixed route, builds an occupancy map from lidar
   and odometry, and saves the map as PGM and YAML files.
2. The navigation workflow loads that map, initializes AMCL, and sends two
   goals through Nav2's `BasicNavigator` API.

The second workflow is also the smoke test:

```bash
make smoke
```

It builds the current image, starts the same headless stack used by the demo,
and exits successfully only when both goals return `SUCCEEDED`. The whole run
has a 180-second wall-clock limit by default. That number came from an
observed run of roughly 90 seconds at a real-time factor near 0.99, with a
two-times margin. It remains configurable through `SMOKE_TIMEOUT`.

This behavioral test matters because every layer before motion can appear
healthy on its own:

```text
lidar + odometry
       |
       v
slam_toolbox ---> saved occupancy map
                          |
                          v
                   AMCL localization
                          |
                          v
goal ---> planner ---> controller ---> /cmd_vel ---> simulated robot
```

A visible map proves that sensing works. A visible path proves that planning
works. Neither proves that a velocity command reaches the robot.

## Why we used a conventional stack

We started with the desired behavior and the host constraints. A
Robium-assisted architecture pass selected ROS 2 Jazzy, Gazebo Harmonic,
Nav2, `slam_toolbox`, and the TurtleBot 3 Burger Cam.

The choices were intentionally ordinary. This project was about integrating
the standard navigation path, not evaluating planners or training a policy.
The Burger provides the lidar and odometry the task needs without adding a
camera to a software-rendered simulation. Jazzy and Harmonic are a supported
ROS/Gazebo pairing, and the TurtleBot packages supply the model, world, and a
useful starting configuration for Nav2.

Docker was less optional. ROS 2 and Gazebo do not run natively on macOS, and
the application needed to work from a clean checkout. One image therefore
contains the simulator, ROS packages, application launch files, saved map,
tests, and browser viewer. Compose profiles expose the individual scenarios:
simulation, SLAM, navigation, demo, and test.

For an interactive run, the public path is deliberately short:

```bash
make build
make demo
```

The viewer is then available on port 8765 with the map, scan, transforms,
costmaps, and planned path already arranged. The footage above is from this
simulation; the application has not been tested on a physical TurtleBot.

## Failure 1: two processes owned SLAM

Our initial SLAM launch combined two reasonable instructions:

- start Nav2's bringup with `slam:=True`;
- include `slam_toolbox`'s online asynchronous launch file.

Together they were wrong. On Jazzy, that Nav2 bringup path already starts
`slam_toolbox`. Adding the second launch created another SLAM node and another
lifecycle owner. Goals then failed around lifecycle transitions and action
server startup.

The important question was not “which SLAM parameter is wrong?” but “who is
responsible for starting this node?” There should be one answer.

We chose to launch the navigation servers directly instead of continuing to
wrap the stock bringup. That decision also solved two constraints elsewhere in
the application:

- the stock navigation launch fixes lifecycle-manager settings that we needed
  to control for Docker Desktop;
- package-share substitutions in the TurtleBot parameter file needed
  `ParameterFile(..., allow_substs=True)` to resolve before reaching a node.

The resulting launch files are longer than a stock include. They are also
explicit: every server appears once, the velocity remappings are visible, and
one lifecycle manager receives the complete node list.

This is not a general argument against `nav2_bringup`. It is a useful default.
For this application, direct composition became simpler once we needed to
change behavior hidden inside that default.

## Failure 2: a VM pause looked like a dead Nav2 server

During activation and the first goal, Docker Desktop sometimes paused the
container long enough for the lifecycle manager to miss bond heartbeats. It
then reported a critical server failure even though the server had not
actually crashed.

The observed pause was around eight seconds. That exceeded the configured
bond timeout, so a host scheduling delay was interpreted as a failed ROS
process.

Because the application owns its lifecycle manager, its simulation launch can
set:

```python
{
    'autostart': True,
    'bond_timeout': 0.0,
    'node_names': lifecycle_nodes,
}
```

Setting `bond_timeout` to zero disables bond checking. That trade-off is
acceptable for this single-container demo: if a server really exits, the
launch system can respawn it, although a respawned lifecycle node returns
unconfigured and is not automatically reactivated. It would be the wrong
default for a physical robot, where losing a navigation server must be
detected and handled safely.

The broader lesson was to inspect the layer below the reported failure. A
lifecycle error can be caused by lifecycle configuration, but it can also be
the first visible symptom of the runtime pausing underneath it.

## Failure 3: `/cmd_vel` existed, but its endpoints disagreed

Once the stack stayed active, Nav2 accepted a goal and produced a path. The
robot remained still because the two ends of `/cmd_vel` used different ROS
message types.

The TurtleBot 3 Gazebo integration on this Jazzy setup subscribes to
`geometry_msgs/TwistStamped`. A publisher using `geometry_msgs/Twist` can use
the same topic name without ever matching that subscriber. ROS does not
convert one type into the other, and the absence of a connection is easy to
miss in a busy launch log.

This command made the mismatch visible:

```bash
ros2 topic info -v /cmd_vel
```

It reports the type and QoS information for each publisher and subscriber,
which is more useful here than checking that the topic merely exists.

The project configuration enables stamped velocity commands in every Nav2
component that may publish them:

```yaml
enable_stamped_cmd_vel: true
```

That includes the controller, velocity smoother, behavior server, collision
monitor, and docking server. Applying the setting only to the main controller
would leave recovery or safety behavior on a different interface.

The collision monitor exposed a second issue on the same command path. The
simulated Burger lidar publishes at about 5 Hz, one scan every 0.2 seconds.
The starting configuration also treated a source as stale after 0.2 seconds.
Normal timing variation was therefore enough to reject a valid scan and stop
the robot. The application gives the scan source a one-second timeout:

```yaml
source_timeout: 1.0
```

The value is a project setting, not a recommended universal default. What
matters is leaving real margin above the expected sensor period.

## Failure 4: Gazebo and the saved map had different origins

The last problem appeared in scripted navigation. We selected goal
coordinates from the Gazebo world, sent them in the `map` frame, and saw the
same positional offset on every attempt.

The robot spawns at `(-2.0, -0.5)` in Gazebo. For this mapping run,
`slam_toolbox` established the map origin at that starting pose. The same
point was therefore `(0.0, 0.0)` in the saved map:

```text
Gazebo world                 saved map

(-2.0, -0.5)      <---->    (0.0, 0.0)

map_x = world_x + 2.0
map_y = world_y + 0.5
```

The saved map retains that frame convention. Clicking a goal in the viewer
naturally gives a map-frame pose, but code that starts with world coordinates
must convert them. The application records that conversion beside the default
goals in `send_goals.py` instead of leaving it as unexplained numbers.

This also changed our debugging order. Before adjusting a costmap or planner,
we now check that the full `map -> odom -> base_link` transform exists, that
timestamps use the same clock, and that a goal is expressed in the frame named
in its header.

## Why the scenarios share one container

We initially considered splitting simulation, navigation, and visualization
into separate containers. On Docker Desktop for macOS, DDS discovery across
those container boundaries added another source of uncertainty. We did not
need that separation for one simulated robot, so each scenario now keeps its
ROS processes in a single container and network namespace.

This choice is narrow rather than architectural doctrine. A native Linux
deployment, multiple robots, or independently deployed services would justify
revisiting the transport and container boundaries. Here, one container made
local behavior repeatable and produced one artifact for the hosted demo.

## What the smoke test actually proves

`make smoke` exercises the saved-map navigation path. The goal sender:

1. publishes the initial pose AMCL needs before it can establish
   `map -> odom`;
2. waits for Nav2 to become active;
3. sends the two map-frame goals `(3.7, 0.5)` and `(0.3, 0.5)` in sequence;
4. requires `TaskResult.SUCCEEDED` for each goal;
5. returns a non-zero exit code on timeout or any other result.

An outer shell timeout also covers the activation phase. This is intentional:
the goal sender's own deadline starts only after `waitUntilNav2Active()`, so a
broken transform or lifecycle transition could otherwise hang the test before
its timer began.

The test proves that one known robot, world, saved map, configuration, and goal
pair complete the navigation loop in simulation. It does not measure route
optimality, robustness across randomized worlds, recovery success, or
real-robot behavior. Those would need different tests and, for hardware,
different safety decisions.

## The debugging order we kept

The failures arrived from different parts of the stack, but they left us with
a useful order of operations:

1. Confirm that `/clock` advances and every simulated node uses simulation
   time.
2. Confirm there is exactly one owner for SLAM and one lifecycle manager for
   the intended navigation servers.
3. Set AMCL's initial pose and verify `map -> odom -> base_link` before tuning
   navigation.
4. Inspect both endpoints of `/cmd_vel`, including message types and QoS.
5. Compare sensor periods with freshness and watchdog timeouts.
6. Express every scripted pose in the frame named in its message header.
7. Run an end-to-end behavioral test, not just process and topic checks.

Most of our time on this application was spent at interfaces: launch ownership,
runtime timing, message contracts, and coordinate frames. Once those were
consistent, the conventional Nav2 stack did the conventional job we selected
it for.

The application source, launch files, saved map, and smoke test are available
in the [Robium applications repository](https://github.com/robium-ai/robium-apps/tree/main/indoor-navigation).
