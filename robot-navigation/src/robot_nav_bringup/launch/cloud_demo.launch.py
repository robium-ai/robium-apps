"""Hosted Robot Navigation workflow with an IDLE-first control panel.

The session manager owns Gazebo and starts mapping or localization only when
the Dashboard requests it. The public port belongs to demo_gateway; the ROS
WebSocket bridge remains private on port 8766.
"""

from launch import LaunchDescription
from launch.actions import ExecuteProcess
from launch_ros.actions import Node


def generate_launch_description():
    gateway = ExecuteProcess(
        cmd=['python3', '/ws/scripts/demo_gateway.py'], output='screen')
    session = Node(
        package='robot_nav_bringup', executable='session_manager',
        name='session_manager', output='screen', parameters=[{
            'map_name': 'map',
            'world': 'furnished_house',
            'maps_root': '/ws/maps',
        }])
    relay = Node(
        package='robot_nav_bringup', executable='teleop_relay',
        name='teleop_relay', output='screen',
        parameters=[{'use_sim_time': True}])
    bridge = Node(
        package='foxglove_bridge', executable='foxglove_bridge',
        name='foxglove_bridge', output='screen', parameters=[{
            'port': 8766,
            'use_sim_time': True,
        }])
    status = Node(
        package='robot_nav_bringup', executable='cloud_demo_status',
        name='cloud_demo_status', output='screen',
        parameters=[{'use_sim_time': True}])
    return LaunchDescription([gateway, session, relay, bridge, status])
