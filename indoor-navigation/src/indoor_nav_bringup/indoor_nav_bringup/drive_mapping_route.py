#!/usr/bin/env python3
"""Drive a staged route through turtlebot3_house under SLAM, then save the map."""
import subprocess
import sys

import rclpy
from geometry_msgs.msg import PoseStamped
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult

SCENARIO = 'turtlebot3_house'
# Staged MAP-frame goals. slam_toolbox anchors map (0, 0) at the spawn pose
# (Gazebo world -2.0, -0.5). Each point is visible from the preceding scan,
# so Nav2 can plan through the initially unknown house instead of jumping to
# an unreachable frontier. Verified live on macOS with Gazebo Harmonic.
HOUSE_ROUTE = [
    (2.0, 0.0),
    (3.0, 0.2),
    (3.4, 0.8),
    (3.4, 1.1),
    (4.5, 0.9),
    (5.5, 0.9),
    (5.1, 1.8),
    (5.7, 3.2),
]
MAP_OUT = '/ws/maps/map'


def make_pose(nav, x, y):
    p = PoseStamped()
    p.header.frame_id = 'map'
    p.header.stamp = nav.get_clock().now().to_msg()
    p.pose.position.x = float(x)
    p.pose.position.y = float(y)
    p.pose.orientation.w = 1.0
    return p


def main():
    rclpy.init()
    nav = BasicNavigator()
    # SLAM provides map->odom; no AMCL, no initial pose needed.
    nav.waitUntilNav2Active(localizer='slam_toolbox')

    reached = 0
    for i, (x, y) in enumerate(HOUSE_ROUTE):
        for attempt in (1, 2):  # one retry: map may still be growing
            nav.goToPose(make_pose(nav, x, y))
            while not nav.isTaskComplete():
                rclpy.spin_once(nav, timeout_sec=1.0)
            result = nav.getResult()
            print(f'waypoint {i} map({x},{y}) attempt {attempt}: {result}',
                  flush=True)
            if result == TaskResult.SUCCEEDED:
                reached += 1
                break

    if reached != len(HOUSE_ROUTE):
        print(f'FAIL: only {reached}/{len(HOUSE_ROUTE)} waypoints reached',
              flush=True)
        sys.exit(1)

    print(f'{reached}/{len(HOUSE_ROUTE)} waypoints reached; saving map...',
          flush=True)
    save = subprocess.run(
        ['ros2', 'run', 'nav2_map_server', 'map_saver_cli', '-f', MAP_OUT,
         '--ros-args', '-p', 'use_sim_time:=true'],
        timeout=60)
    sys.exit(save.returncode)


if __name__ == '__main__':
    main()
