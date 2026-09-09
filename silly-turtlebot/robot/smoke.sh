#!/usr/bin/env bash
set -eo pipefail

robot_root="$(cd "$(dirname "$0")" && pwd)"
ros_distro="${ROS_DISTRO:-humble}"
source "/opt/ros/${ros_distro}/setup.bash"
[ ! -f /etc/turtlebot4/setup.bash ] || source /etc/turtlebot4/setup.bash
source "${robot_root}/ros_ws/install/setup.bash"
set -u

actions="$(ros2 action list -t)"
grep -q '/navigate_to_pose.*nav2_msgs/action/NavigateToPose' <<<"$actions"
grep -q '/drive_on_heading.*nav2_msgs/action/DriveOnHeading' <<<"$actions"
grep -q '/spin.*nav2_msgs/action/Spin' <<<"$actions"
timeout 10 ros2 topic echo --once \
  /scan >/dev/null
timeout 10 ros2 topic echo --once \
  /odom --qos-reliability best_effort >/dev/null
timeout 10 ros2 topic echo --once \
  /map --qos-durability transient_local >/dev/null
curl --fail --silent http://127.0.0.1:8088/v1/health | \
  python3 -c 'import json,sys; h=json.load(sys.stdin); assert h["status"] == "ok"; assert h["navigate_to_pose"]; assert h["drive_on_heading"]; assert h["spin"]'
if [ -n "${SILLY_CAMERA_URL:-}" ]; then
  curl --fail --silent "${SILLY_CAMERA_URL%/}/health" | \
    python3 -c 'import json,sys; h=json.load(sys.stdin); assert h["status"] == "ok"; assert h["fresh"]'
  curl --fail --silent "${SILLY_CAMERA_URL%/}/frame.jpg" >/dev/null
fi
echo "SILLY TURTLEBOT ROBOT SMOKE PASS"
