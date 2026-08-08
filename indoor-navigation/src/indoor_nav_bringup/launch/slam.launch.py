"""SLAM scenario: sim + slam_toolbox (online_async) + Nav2 navigation servers.

The Nav2 server set (and the hard-won reasoning behind launching it
directly rather than via nav2_bringup) lives in nav2_servers.launch.py,
shared with mapping.launch.py so the two scenarios cannot drift apart.

This scenario is the SCRIPTED one: drive_mapping_route drives a fixed
route and saves a map, wrapped by scripts/run_slam.sh with SLAM_TIMEOUT so
no failure mode is an unbounded hang. For driving the robot yourself, see
mapping.launch.py.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource


def generate_launch_description():
    pkg = get_package_share_directory('indoor_nav_bringup')
    slam_toolbox = get_package_share_directory('slam_toolbox')

    sim = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(pkg, 'launch', 'sim.launch.py')))

    slam = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(slam_toolbox, 'launch', 'online_async_launch.py')),
        launch_arguments={
            'use_sim_time': 'true',
            'slam_params_file': os.path.join(pkg, 'config', 'slam_params.yaml'),
        }.items())

    nav2 = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg, 'launch', 'nav2_servers.launch.py')))

    return LaunchDescription([sim, slam, nav2])
