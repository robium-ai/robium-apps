#!/usr/bin/env bash
set -eo pipefail

robot_root="$(cd "$(dirname "$0")" && pwd)"
ros_distro="${ROS_DISTRO:-humble}"
source "/opt/ros/${ros_distro}/setup.bash"
[ ! -f /etc/turtlebot4/setup.bash ] || source /etc/turtlebot4/setup.bash
set -u

cd "${robot_root}/ros_ws"
if [ ! -f /etc/ros/rosdep/sources.list.d/20-default.list ]; then
  sudo -n rosdep init
fi
rosdep update --rosdistro "${ros_distro}"
# ament_python is the colcon build type, not a resolvable rosdep system key on
# the TurtleBot 4 Humble image. The image already ships the colcon ROS plugin.
rosdep install --from-paths src -y --ignore-src --skip-keys ament_python
colcon build --symlink-install
