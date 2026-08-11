# tb4-teleop — architecture brief

**Phase 1 (this brief): browser teleoperation of a real TurtleBot 4 — navigation.**
Camera (OAK-D) and SLAM mapping are later phases. Full spec:
`docs/superpowers/specs/2026-07-24-tb4-teleop-design.md`.

## Overview

Drive a physical TurtleBot 4 from a browser with live sensor feedback, and dock/undock
from the browser too. The Mac needs **no ROS** — a `foxglove_bridge` on the robot exposes
a WebSocket that Foxglove Studio connects to. This is the repo's first **real-hardware**
app (all prior apps are simulation).

## Hardware (verified 2026-07-24)

| | |
| --- | --- |
| Platform | TurtleBot 4 (iRobot Create 3 base + Raspberry Pi 4 + RPLIDAR + OAK-D) |
| OS / ROS | Ubuntu 22.04.4 aarch64 · ROS 2 **Humble** · CycloneDDS · `ROS_DOMAIN_ID=0` |
| Robot IP | `<ROBOT_IP>` supplied by the operator |
| Client IP | `<CLIENT_IP>` on a reachable network |
| SSH | `ubuntu@<ROBOT_IP>` using key authentication |
| Bridge | `foxglove_bridge` 3.4.2 on `:8765`; WS subprotocol `foxglove.sdk.v1` |
| `/cmd_vel` | `geometry_msgs/msg/Twist` |

mDNS is inactive — use the IP, not `ubuntu.local`.

## Architecture & data flow

```
Browser (Foxglove Studio)            TurtleBot 4 (<ROBOT_IP>)
 Teleop panel  --/cmd_vel Twist-->    foxglove_bridge :8765  <--localhost DDS-->  ROS graph
 UNDOCK/DOCK   --/teleop/{dock,        tb4_teleop_actions node --/dock,/undock actions--> Create 3
                undock} Empty-->
 3D panel      <--/scan,/tf,model--    RPLIDAR (Pi-local)
 readouts      <--/battery,/dock,      Create 3 base (usb0): /motion_control, battery, dock…
                /hazard--
        \------------- ws://<ROBOT_IP>:8765 (TCP) -------------/
```

**Two independent paths — critical for debugging:**
- **LiDAR `/scan`** is *Pi-local* (RPLIDAR→Pi→bridge→browser). It works even when the base
  is disconnected, so seeing the scan proves the browser↔Pi path but says **nothing** about
  driving.
- **Driving + base sensors** require the *Pi↔Create 3* path over `usb0`. The base is a
  separate computer with its own DDS.

**Dock/undock** are ROS 2 *actions*, which Foxglove can't call. `robot/teleop_actions.py`
bridges `std_msgs/Empty` topic triggers (`/teleop/dock`, `/teleop/undock`) to the Create 3
`Dock`/`Undock` actions; Foxglove **Publish panels** are the buttons.

## Environment & reproducibility

The "environment" is the robot + committed artifacts + **two one-time robot-side setup
steps** (see README "Robot setup"): (1) install `ros-humble-foxglove-bridge`, (2) apply the
CycloneDDS discovery fix (below). `make bridge` then deploys `teleop_actions.py` and
launches both the bridge and the helper over SSH; the browser imports
`foxglove/tb4-teleop-layout.json`. No container on the Pi in Phase 1.

## Testing / pass bar

- `make smoke` — **hardware-in-the-loop** (robot powered on RobotWiFi): robot reachable,
  bridge WS up, `/scan` flowing, `/cmd_vel` accepts a zero Twist. Not CI-runnable without
  the robot (accepted).
- **Real pass bar (met 2026-07-24):** a human drives the real robot from the Foxglove
  Teleop panel, and UNDOCK/DOCK buttons work.

## Battle scars (see `learnings/2026-07-24.md`)

- **Base invisible to the Pi → robot won't drive.** Root cause: the robot's
  `/etc/turtlebot4/setup.bash` sets `CYCLONEDDS_URI` to a config whose `<Interfaces>` block
  restricts CycloneDDS to `wlan0`, blocking discovery of the Create 3 over `usb0`. **Fix:
  disable that `CYCLONEDDS_URI` export** (CycloneDDS then defaults to all interfaces),
  restart `turtlebot4.service` and the bridge. Enabling `usb0` in the xml did NOT suffice;
  only dropping the restriction worked. `/scan` working masks this entirely.
- **Clock is a red herring.** Pi has no RTC + no NTP on RobotWiFi → reboots to a stale
  date; the base syncs NTP *from* the Pi. Don't manually jump the Pi clock (creates skew)
  and **don't reboot the Pi** (loses the clock). Matching clocks did not fix discovery.
- **Base topics need `--qos-reliability best_effort`** to `ros2 topic echo` (Create 3 is
  best-effort); `ros2 topic pub --once /cmd_vel` **hangs** (split-DDS hides the base
  subscriber) — use `-w 0`.
- **Create 3 storage mode:** 7-sec button hold cuts battery to robot + Pi; **only docking
  re-powers it**. `ros2 topic info /cmd_vel` shows 0 subscribers even when working
  (base subscribes in a separate DDS realm).
- **Tooling:** kill a stale bridge by port (`fuser -k 8765/tcp`), never
  `pkill -f foxglove_bridge` (self-matches the launch SSH → exit 255). macOS puts wired
  ahead of Wi-Fi in service order → route internet down the dead-end robot LAN; reorder
  Wi-Fi above the USB LAN.

## Phase roadmap

1. **Navigation (done):** drive + `/scan` + battery/dock/hazard + dock/undock buttons.
2. **Camera:** stream OAK-D `/oakd/rgb/image_raw` into a Foxglove Image panel.
3. **Mapping:** slam_toolbox to build/save a map while teleop-driving.
