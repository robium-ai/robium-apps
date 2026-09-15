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
grep -q '/drive_distance.*irobot_create_msgs/action/DriveDistance' <<<"$actions"
grep -q '/spin.*nav2_msgs/action/Spin' <<<"$actions"
grep -q '/dock.*irobot_create_msgs/action/Dock' <<<"$actions"
grep -q '/undock.*irobot_create_msgs/action/Undock' <<<"$actions"
timeout 10 ros2 topic echo --once \
  /scan >/dev/null
timeout 10 ros2 topic echo --once \
  /odom --qos-reliability best_effort >/dev/null
timeout 10 ros2 topic echo --once \
  /diagnostics >/dev/null
timeout 10 ros2 topic echo --once \
  /global_costmap/costmap >/dev/null
ros2 param get /bt_navigator global_frame | grep -q 'odom'
ros2 param get /global_costmap/global_costmap global_frame | grep -q 'odom'
ros2 param get /global_costmap/global_costmap rolling_window | grep -q 'True'
ros2 lifecycle get /bt_navigator | grep -q 'active'
ros2 lifecycle get /planner_server | grep -q 'active'
ros2 lifecycle get /controller_server | grep -q 'active'
ros2 param get /motion_control safety_override | grep -q 'full'
nodes="$(ros2 node list)"
grep -q '^/joy_linux_node$' <<<"$nodes"
grep -q '^/teleop_twist_joy_node$' <<<"$nodes"
grep -q '^/gamepad_actions$' <<<"$nodes"
grep -q '^/remote_joy$' <<<"$nodes"
topics="$(ros2 topic list -t)"
grep -q '/joy.*sensor_msgs/msg/Joy' <<<"$topics"
grep -Fq \
  '/orin/oakd/preview/image_raw/compressed [sensor_msgs/msg/CompressedImage]' \
  <<<"$topics"
timeout 20 ros2 topic echo --once \
  /orin/oakd/preview/image_raw/compressed sensor_msgs/msg/CompressedImage \
  --qos-reliability reliable >/dev/null
if grep -Eq '^/(async_)?slam_toolbox$' <<<"$nodes"; then
  echo "SLAM must not run in odom navigation mode" >&2
  exit 1
fi
curl --fail --silent http://127.0.0.1:8088/v1/health | \
  python3 -c 'import json,sys; h=json.load(sys.stdin); assert h["status"] == "ok"; assert h["navigate_to_pose"]; assert h["drive_distance"]; assert h["spin"]; assert h["dock"]; assert h["undock"]; assert 0 <= h["battery_percentage"] <= 100'
if [ -n "${SILLY_CAMERA_URL:-}" ]; then
  curl --fail --silent "${SILLY_CAMERA_URL%/}/health" | \
    python3 -c 'import json,sys; h=json.load(sys.stdin); assert h["status"] == "ok"; assert h["fresh"]'
  curl --fail --silent "${SILLY_CAMERA_URL%/}/frame.jpg" >/dev/null
fi
echo "SILLY TURTLEBOT ROBOT SMOKE PASS"
