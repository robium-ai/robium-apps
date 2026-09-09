"""Physical TurtleBot 4 mapless Nav2 and guarded semantic bridge."""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource


def generate_launch_description():
    turtlebot_navigation = Path(
        get_package_share_directory("turtlebot4_navigation")
    )
    silly_share = Path(get_package_share_directory("silly_turtlebot_ros"))

    nav2 = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            str(turtlebot_navigation / "launch" / "nav2.launch.py")
        ),
        launch_arguments={
            "use_sim_time": "false",
            "params_file": str(silly_share / "config" / "nav2_odom.yaml"),
        }.items(),
    )
    bridge = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            str(silly_share / "launch" / "bridge.launch.py")
        ),
        launch_arguments={
            "bind_host": "0.0.0.0",
            # The contest OAK-D is attached to the Orin and reaches Gemini
            # through SILLY_CAMERA_URL, not through the Pi's ROS graph.
            "primary_camera_topic": "",
        }.items(),
    )
    return LaunchDescription([nav2, bridge])
