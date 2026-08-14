"""Restartable mapping or localization stack; simulation is owned separately."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PythonExpression


def generate_launch_description():
    pkg = get_package_share_directory('indoor_nav_bringup')
    slam_toolbox = get_package_share_directory('slam_toolbox')
    mode = LaunchConfiguration('mode')
    mapping = PythonExpression(["'", mode, "' == 'mapping'"])
    localization = PythonExpression(["'", mode, "' == 'localization'"])

    slam = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(slam_toolbox, 'launch', 'online_async_launch.py')),
        condition=IfCondition(mapping),
        launch_arguments={
            'use_sim_time': 'true',
            'slam_params_file': os.path.join(pkg, 'config', 'slam_params.yaml'),
        }.items())
    nav_mapping = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg, 'launch', 'nav2_servers.launch.py')),
        condition=IfCondition(mapping))
    nav_localization = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg, 'launch', 'nav2_servers.launch.py')),
        condition=IfCondition(localization),
        launch_arguments={
            'localization': 'true',
            'map_yaml': LaunchConfiguration('map_yaml'),
        }.items())

    return LaunchDescription([
        DeclareLaunchArgument(
            'mode', choices=['mapping', 'localization'],
            description='the mutually exclusive navigation session'),
        DeclareLaunchArgument('map_yaml', default_value='/ws/maps/map.yaml'),
        slam,
        nav_mapping,
        nav_localization,
    ])
