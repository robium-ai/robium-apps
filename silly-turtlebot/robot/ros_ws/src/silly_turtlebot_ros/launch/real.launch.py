"""Physical TurtleBot 4 mapless Nav2 and guarded semantic bridge."""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    external_camera_url = LaunchConfiguration("external_camera_url")
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
    gamepad_actions = Node(
        package="silly_turtlebot_ros",
        executable="gamepad_actions",
        name="gamepad_actions",
        output="screen",
        parameters=[
            {
                # TurtleBot 4's stock joy/teleop nodes already start at boot.
                # On the paired Stadia controller: A=0, B=1, L1=4, R1=5.
                "undock_button": 0,
                "dock_button": 1,
                "enable_button": 4,
                "turbo_button": 5,
            }
        ],
    )
    remote_joy = Node(
        package="silly_turtlebot_ros",
        executable="remote_joy",
        name="remote_joy",
        output="screen",
        parameters=[
            {
                "allowed_hosts": ["10.42.0.2", "192.168.0.51"],
                "port": 8766,
            }
        ],
    )
    external_camera_relay = Node(
        package="silly_turtlebot_ros",
        executable="external_camera_relay",
        name="external_camera_relay",
        output="screen",
        parameters=[
            {
                "camera_url": external_camera_url,
                "topic": "/orin/oakd/preview/image_raw/compressed",
                "frame_id": "oakd_rgb_camera_optical_frame",
                "publish_fps": 1.0,
                "request_timeout_s": 2.0,
            }
        ],
    )
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "external_camera_url",
                default_value="http://192.168.0.51:8081/preview.jpg",
                description="Orin OAK-D JPEG endpoint relayed into ROS 2",
            ),
            nav2,
            bridge,
            external_camera_relay,
            remote_joy,
            gamepad_actions,
        ]
    )
