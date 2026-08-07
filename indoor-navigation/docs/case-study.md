---
title: From an empty map to autonomous navigation with ROS 2 and Nav2
summary: What we learned building a reproducible SLAM and navigation loop with Gazebo, Nav2, and TurtleBot 3, running headlessly in Docker on Apple Silicon.
app: indoor-navigation
date: 2026-08-05
hero: assets/trailer.gif
hero_alt: Simulated TurtleBot 3 driving itself to a clicked goal in the bundled browser viewer (simulation footage)
featured: true
---

The first encouraging sign was a wall of laser points in the browser.
Gazebo was running inside an ARM64 Docker container on a MacBook, there was
no GPU attached, and yet the TurtleBot's simulated lidar was publishing at
roughly real-time speed.

That was only the first layer of the problem. We wanted the robot to explore
the world, save what it learned, restart against that map, localize itself,
and drive to a destination selected in the browser. More importantly,
someone else had to be able to reproduce the entire sequence from a clean
clone.

On paper this is the standard ROS 2 navigation stack: Gazebo,
`slam_toolbox`, AMCL, and Nav2. In practice, making those pieces work
together exposed several boundaries that introductory tutorials tend to
hide: two lifecycle managers trying to own the same node, velocity messages
that almost matched, map coordinates with an unexpected origin, and
discovery behavior that changed inside Docker.

This is how we built the system, what broke along the way, and the checks we
now run before touching a planner parameter.

## The loop we wanted to prove

A navigation demo can look alive while very little has actually been
verified. Processes may be running, a map may be visible, and a planned path
may appear even though commands never reach the robot. We therefore defined
the result as a complete loop:

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
goal ---> Nav2 planner ---> controller ---> /cmd_vel ---> robot
```

During mapping, `slam_toolbox` combines lidar scans and odometry into an
occupancy grid. We save that grid as a PGM image plus a YAML description.
During navigation, the map server loads the saved grid and AMCL estimates
the robot's pose within it. Nav2 builds costmaps, plans a collision-free
route, and continuously produces velocity commands to follow it.

The final test is deliberately behavioral: start the whole stack, send two
goals, and require Nav2 to report `SUCCEEDED` for both within a fixed
timeout. A green process list is not enough.

## Choosing a stack for a Mac without a GPU

We started by giving a Robium-equipped coding agent the outcome and the
machine constraints, rather than prescribing every package. Its architecture
pass selected ROS 2 Jazzy, Gazebo Harmonic, Nav2, `slam_toolbox`, and a
TurtleBot 3 Burger. That is a conventional stack, which was exactly what we
wanted: the experiment was about integration and reproducibility, not a new
planner.

The host changed the shape of the application. ROS 2 and Gazebo would run in
Docker, Gazebo would render headlessly with Mesa's software renderer, and a
browser viewer would replace RViz. We chose the Burger because lidar and
odometry are enough for this pipeline; a camera would have added rendering
cost without helping navigation.

One image contains the simulator, robot model, ROS packages, launch files,
saved map, tests, and the Lichtblick web viewer. Compose profiles select the
scenario: simulation only, SLAM, navigation, the interactive demo, or the
smoke test. From the user's side, the complete experience is:

```bash
make build
make demo
```

Then the browser opens the viewer on port 8765, already connected and laid
out to show the robot, map, laser scan, costmaps, and planned path.

The architecture choice was the easy part. Getting every package to agree
on ownership, time, frames, and message types took most of the work.

## Failure one: we launched SLAM twice

Our first SLAM composition looked reasonable: start Nav2 in SLAM mode and
also include `slam_toolbox`'s online asynchronous launch file. Goals failed,
and the logs filled with lifecycle transition errors:

```text
Unable to start transition 1 from current state inactive
Timed out while waiting for action server to acknowledge goal request
```

The problem was not a map parameter. On ROS 2 Jazzy, Nav2's bringup path with
`slam:=True` already starts a `slam_toolbox` instance. Our extra include
created a second node with the same job. Two lifecycle managers then tried
to configure and activate overlapping parts of the stack.

The durable lesson is simple: choose one owner for SLAM. Either let the Nav2
bringup launch it, or launch the navigation servers and your chosen SLAM
node yourself. Do not combine the two approaches.

We eventually launched the Nav2 servers directly. That also solved two
other problems we had encountered: the stock navigation launch hard-coded
lifecycle-manager settings we needed to change, and substitutions such as
`$(find-pkg-share ...)` were reaching nodes as literal strings. Loading the
configuration through `ParameterFile(..., allow_substs=True)` made those
paths resolve correctly.

Direct launch files are more verbose, but in this application the explicit
ownership was worth it. Each server appears once, every remapping is visible,
and one lifecycle manager controls the complete list.

## Failure two: Docker pauses looked like dead servers

When Nav2 activated, Docker Desktop occasionally stalled for about eight
seconds. The default lifecycle bond timeout was shorter than the stall, so
the lifecycle manager concluded that a healthy server had died:

```text
CRITICAL FAILURE: SERVER controller_server IS DOWN
```

This is a good example of a failure crossing abstraction boundaries. The
ROS process was healthy, the configuration was largely correct, and the
simulator was running. A host-level scheduling pause was being interpreted
as an application-level crash.

Because the stock Jazzy launch file fixes the lifecycle-manager parameters,
we could not repair this through the normal Nav2 parameter file. Owning the
lifecycle manager in our launch composition allowed us to disable its bond
timeout for this single-container demo. We also ran Nav2 as standalone,
respawnable nodes while developing, so one crashing server did not take down
a component container containing everything else.

This is not a recommendation to disable failure detection on a real robot.
It is a reminder that watchdog values have to reflect their runtime. A
laptop VM, a production robot computer, and a cloud container do not have
the same pause behavior.

## Failure three: a path appeared, but the robot did not move

ROS interfaces are strongly typed. A publisher and subscriber can use the
same topic name and still never connect if one expects
`geometry_msgs/Twist` and the other expects `geometry_msgs/TwistStamped`.
The TurtleBot 3 integration on Jazzy uses the stamped form for velocity
commands.

This failure is quiet. Nav2 can plan a valid path, and a command publisher
can appear healthy, while Gazebo ignores every command. The useful check is
not just whether `/cmd_vel` exists:

```bash
ros2 topic info -v /cmd_vel
```

That reveals the types on both ends. Our configuration keeps stamped
commands enabled for every component that can publish velocity, including
the controller, velocity smoother, behavior server, collision monitor, and
docking server:

```yaml
enable_stamped_cmd_vel: true
```

Consistency matters more than the individual switch. Fixing one publisher
while leaving another on the old type can make normal driving work and
recovery behaviors fail later.

We found another timing edge in the same path. The TurtleBot lidar publishes
at about 5 Hz, or once every 0.2 seconds, while the starting collision
monitor configuration allowed only 0.2 seconds before treating the source
as stale. Ordinary jitter was enough to make the monitor reject scans and
zero the velocity command. Increasing the timeout above the sensor period
removed that race.

## Failure four: the map was right and the goal was wrong

Once mapping worked, we scripted goals using coordinates from the Gazebo
world. They were consistently offset. The robot was not confused; we were
mixing two coordinate systems.

`slam_toolbox` establishes the map frame relative to the robot's starting
pose. Our TurtleBot spawned at world coordinate `(-2.0, -0.5)`, but that
same physical location became `(0.0, 0.0)` in the SLAM map:

```text
Gazebo world                SLAM map

robot starts at             map origin
(-2.0, -0.5)     <---->     (0.0, 0.0)

goal_map = goal_world - robot_start_world
```

The saved map inherits that convention. Goals sent to Nav2 therefore need
map-frame coordinates, not the coordinates used to place objects in the
Gazebo world. Clicking a goal in the viewer naturally produces a map-frame
pose; scripted tests must perform the conversion themselves.

This was a small fix with a large debugging lesson: before tuning costmaps
or planners, verify that the transform chain `map -> odom -> base_link`
exists and that the goal is expressed in the frame named in its header.
Many apparent planning failures are actually time or transform failures.

## Why one container was more reliable than several

Our original instinct was to put the simulator, navigation stack, and
viewer bridge in separate containers. On Docker Desktop for macOS, that
made ROS 2 discovery less predictable because DDS multicast did not cross
the bridge boundaries the way it would on a native Linux host.

For this single-robot application, we chose one container per scenario.
Processes still have normal ROS node boundaries, but they share one network
namespace. Compose is used to select complete scenarios rather than to
isolate individual nodes.

That is an environment-specific tradeoff, not a universal ROS architecture.
For a multi-robot system or native Linux deployment, separate containers,
explicit DDS configuration, or another transport may be the better choice.
Here, one container made the local run deterministic and also gave us one
artifact for the hosted demo.

## Testing motion instead of launch files

The smoke test became the most important part of the application. It runs
the same headless simulation and Nav2 stack as the interactive demo, waits
for the managed nodes to become active, initializes localization, and sends
two poses through `nav2_simple_commander`. It fails if either goal is
rejected, aborted, canceled, or exceeds the timeout.

```bash
make smoke
```

On the development Mac, the complete run takes about 90 seconds once the
image is warm. Gazebo maintains a real-time factor close to 1.0 through
software rendering, which was better than we expected from a GPU-less
container. The outer test timeout is 180 seconds so a broken launch cannot
hang indefinitely.

We also tested the instructions, not just the code: a clean copy outside
the repository ran `make build && make demo`, the bundled viewer connected
without an account or manual layout import, and a clicked goal drove the
robot. Documentation that has never been run from a clean checkout is still
an untested interface.

The demo remains simulation-only. A 360-sample lidar running through
software rendering says little about a camera-heavy workload, and none of
the Nav2 parameters here should be treated as a sim-to-real calibration.
The point is narrower: the complete classical navigation loop is visible,
repeatable, and tested on an ordinary development laptop.

## The debugging order we would use next time

The project changed how we approach a Nav2 system that “does nothing.” We
now check the stack from its foundations upward:

1. Confirm Gazebo's `/clock` is advancing and every simulated node uses
   simulation time.
2. Confirm `/scan` and `/odom` are publishing at plausible rates.
3. Verify the full `map -> odom -> base_link` transform chain. With AMCL,
   remember that `map -> odom` does not appear until an initial pose is set.
4. Check that each Nav2 lifecycle node is active.
5. Inspect the publisher and subscriber types on `/cmd_vel`.
6. Check that sensor freshness limits are comfortably above sensor periods.
7. Confirm the goal is in the map frame and lies inside known free space.
8. Only then change the planner, controller, footprint, or costmap tuning.

The Robium skills helped select a sensible starting architecture and turned
the failures we encountered into reusable guidance. But the useful part of
the process was not that an agent produced a launch file quickly. It was
that the finished application preserved the evidence: observed errors,
specific fixes, a saved map, an end-to-end test, and a path another developer
can run without recreating our environment.

You can explore the implementation in this repository and run the same
system with `make demo`. If your own robot plans but refuses to move, start
with the checklist above. The planner is probably not the first thing that
needs tuning.
