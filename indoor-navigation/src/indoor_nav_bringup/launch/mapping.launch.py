"""Persistent dashboard with an IDLE-first, restartable robot session."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    world_arg = DeclareLaunchArgument(
        'world', default_value='furnished_house',
        choices=['furnished_house', 'tugbot_warehouse'])
    map_name_arg = DeclareLaunchArgument('map_name', default_value='map')

    session = Node(
        package='indoor_nav_bringup', executable='session_manager',
        name='session_manager', output='screen', parameters=[{
            'map_name': LaunchConfiguration('map_name'),
            'world': LaunchConfiguration('world'),
            'maps_root': '/ws/maps',
        }])
    relay = Node(
        package='indoor_nav_bringup', executable='teleop_relay',
        name='teleop_relay', output='screen',
        parameters=[{'use_sim_time': True}])
    foxglove = Node(
        package='foxglove_bridge', executable='foxglove_bridge',
        output='screen', parameters=[{'port': 8765, 'use_sim_time': True}])
    viz = ExecuteProcess(
        cmd=['python3', '/ws/scripts/viz_server.py', '--port', '8080',
             '--layout', '/opt/lichtblick/mapping-layout.json'],
        output='screen')

    return LaunchDescription([
        world_arg, map_name_arg, session, relay, foxglove, viz,
    ])
