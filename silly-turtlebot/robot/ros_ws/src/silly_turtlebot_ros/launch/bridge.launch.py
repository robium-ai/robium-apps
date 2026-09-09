from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    share = Path(get_package_share_directory("silly_turtlebot_ros"))
    arguments = [
        DeclareLaunchArgument(
            "waypoints_file", default_value=str(share / "config" / "waypoints.yaml")
        ),
        DeclareLaunchArgument("bind_host", default_value="127.0.0.1"),
        DeclareLaunchArgument("port", default_value="8088"),
        DeclareLaunchArgument("navigate_action", default_value="/navigate_to_pose"),
        DeclareLaunchArgument(
            "drive_on_heading_action", default_value="/drive_on_heading"
        ),
        DeclareLaunchArgument("spin_action", default_value="/spin"),
        DeclareLaunchArgument("dock_action", default_value="/dock"),
        DeclareLaunchArgument("undock_action", default_value="/undock"),
        DeclareLaunchArgument("forward_speed_mps", default_value="0.12"),
        DeclareLaunchArgument(
            "primary_camera_topic",
            default_value="/oakd/rgb/preview/image_raw/compressed",
        ),
        DeclareLaunchArgument("secondary_camera_topic", default_value=""),
        DeclareLaunchArgument("tts_command", default_value="espeak-ng"),
    ]
    bridge = Node(
        package="silly_turtlebot_ros",
        executable="bridge",
        name="silly_turtlebot_bridge",
        output="screen",
        parameters=[
            {
                "waypoints_file": LaunchConfiguration("waypoints_file"),
                "bind_host": LaunchConfiguration("bind_host"),
                "port": LaunchConfiguration("port"),
                "navigate_action": LaunchConfiguration("navigate_action"),
                "drive_on_heading_action": LaunchConfiguration(
                    "drive_on_heading_action"
                ),
                "spin_action": LaunchConfiguration("spin_action"),
                "dock_action": LaunchConfiguration("dock_action"),
                "undock_action": LaunchConfiguration("undock_action"),
                "forward_speed_mps": LaunchConfiguration("forward_speed_mps"),
                "primary_camera_topic": LaunchConfiguration("primary_camera_topic"),
                "secondary_camera_topic": LaunchConfiguration("secondary_camera_topic"),
                "tts_command": LaunchConfiguration("tts_command"),
            }
        ],
    )
    return LaunchDescription([*arguments, bridge])
