# tb4-teleop — browser teleop of a real TurtleBot 4

Drive a physical TurtleBot 4 from a browser (Foxglove Studio) over Wi-Fi.
Phase 1: navigation (drive + live scan + status). Camera and mapping are later phases.
Spec: `docs/superpowers/specs/2026-07-24-tb4-teleop-design.md`.

## Robot facts (verified 2026-07-24)

| | |
| --- | --- |
| Platform | TurtleBot 4 (Create 3 + RPi 4 + RPLIDAR + OAK-D), ROS 2 Humble |
| Robot IP | `<ROBOT_IP>` (set `ROBOT=<ROBOT_IP>` for the Make targets) |
| Client IP | `<CLIENT_IP>` on the same reachable network |
| SSH | `ubuntu@<ROBOT_IP>` using key authentication |
| Bridge | `foxglove_bridge` 3.4.2 on `:8765`; WS subprotocol `foxglove.sdk.v1` |
| `/cmd_vel` | `geometry_msgs/msg/Twist` (plain Twist) |

mDNS is inactive — use the IP, not `ubuntu.local`. The Create 3 base runs its own FastDDS
on `usb0`; the Pi runs CycloneDDS on `wlan0` — so `ros2 topic info /cmd_vel` shows 0
subscribers even when the base is listening. Motion is confirmed only by driving.

## Robot setup (one-time)

Two robot-side steps a fresh TB4 needs (both persist across reboots):

1. **Install the bridge** (needs internet once — join the robot's Wi-Fi to a network with
   internet, or share via cable):

       ssh ubuntu@<ROBOT_IP> 'sudo apt-get update && sudo apt-get install -y ros-humble-foxglove-bridge'

2. **Fix Create 3 base discovery.** The stock `/etc/turtlebot4/setup.bash` sets
   `CYCLONEDDS_URI` to a config that restricts CycloneDDS to `wlan0`, which **blocks
   discovery of the Create 3 base over `usb0`** — the robot then won't drive (though
   `/scan` still works, masking it). Disable that export so CycloneDDS uses all interfaces:

       ssh ubuntu@<ROBOT_IP> "sudo sed -i 's|^export CYCLONEDDS_URI=|#export CYCLONEDDS_URI=|' /etc/turtlebot4/setup.bash && sudo systemctl restart turtlebot4.service"

   Verify: `ros2 node list` should show `/motion_control`, and
   `ros2 topic echo --once --qos-reliability best_effort /battery_state` should print a
   percentage. See `docs/architecture-brief.md` "Battle scars".

## Usage

    make bridge     # start foxglove_bridge + dock/undock helper on the robot (over SSH)
    make teleop     # print the Foxglove connect URL + layout import hint
    make smoke      # hardware-in-the-loop smoke (robot must be powered on RobotWiFi)

Then open https://app.foxglove.dev → Open connection → `ws://<ROBOT_IP>:8765`,
and import `foxglove/tb4-teleop-layout.json`.

## Safety

The robot moves. First drive: undock onto clear floor, keep speed caps low, supervise.
