#!/usr/bin/env bash
set -eo pipefail

robot_root="$(cd "$(dirname "$0")" && pwd)"
ros_distro="${ROS_DISTRO:-humble}"
source "/opt/ros/${ros_distro}/setup.bash"
[ ! -f /etc/turtlebot4/setup.bash ] || source /etc/turtlebot4/setup.bash
source "${robot_root}/ros_ws/install/setup.bash"
set -u

exec ros2 launch silly_turtlebot_ros bridge.launch.py "$@"
