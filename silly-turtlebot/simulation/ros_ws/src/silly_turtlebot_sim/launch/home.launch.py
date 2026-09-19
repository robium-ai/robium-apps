"""Headless TurtleBot 4 + Nav2 in the pinned furnished-home environment."""

import os
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    AppendEnvironmentVariable,
    ExecuteProcess,
    IncludeLaunchDescription,
    OpaqueFunction,
    RegisterEventHandler,
    SetEnvironmentVariable,
)
from launch.event_handlers import OnProcessExit
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node

from silly_turtlebot_sim.world import (
    ASSET_ROOT,
    SPAWN_X,
    SPAWN_Y,
    WORLD_NAME,
    prepare_world,
)

# TurtleBot 4's Create 3 description carries its own model-scoped Sensors
# system, so this world must not add a second one.
SYSTEMS = (
    ("gz-sim-physics-system", "gz::sim::systems::Physics"),
    ("gz-sim-user-commands-system", "gz::sim::systems::UserCommands"),
    ("gz-sim-scene-broadcaster-system", "gz::sim::systems::SceneBroadcaster"),
    ("gz-sim-imu-system", "gz::sim::systems::Imu"),
)
PREPARED_WORLD = "small_house.silly-turtlebot.world"


def _gazebo(_context):
    ros_gz_sim = get_package_share_directory("ros_gz_sim")
    return [
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(ros_gz_sim, "launch", "gz_sim.launch.py")
            ),
            launch_arguments={
                "gz_args": [
                    "-r -s --headless-rendering --render-engine ogre2 -v2 ",
                    prepare_world(SYSTEMS, PREPARED_WORLD),
                ],
                "on_exit_shutdown": "true",
            }.items(),
        )
    ]


def generate_launch_description():
    package = Path(get_package_share_directory("silly_turtlebot_sim"))
    tb4_bringup = Path(get_package_share_directory("turtlebot4_gz_bringup"))
    tb4_description = Path(get_package_share_directory("turtlebot4_description"))
    tb4_navigation = Path(get_package_share_directory("turtlebot4_navigation"))
    create_description = Path(get_package_share_directory("irobot_create_description"))
    create_bringup = Path(get_package_share_directory("irobot_create_gz_bringup"))
    tb4_gui = Path(get_package_share_directory("turtlebot4_gz_gui_plugins"))
    create_plugins = Path(get_package_share_directory("irobot_create_gz_plugins"))

    resources = [
        AppendEnvironmentVariable("GZ_SIM_RESOURCE_PATH", str(ASSET_ROOT / "models")),
        AppendEnvironmentVariable("GZ_SIM_RESOURCE_PATH", str(tb4_bringup / "worlds")),
        AppendEnvironmentVariable(
            "GZ_SIM_RESOURCE_PATH", str(create_bringup / "worlds")
        ),
        AppendEnvironmentVariable(
            "GZ_SIM_RESOURCE_PATH", str(tb4_description.parent.resolve())
        ),
        AppendEnvironmentVariable(
            "GZ_SIM_RESOURCE_PATH", str(create_description.parent.resolve())
        ),
        SetEnvironmentVariable(
            "GZ_GUI_PLUGIN_PATH",
            ":".join([str(tb4_gui / "lib"), str(create_plugins / "lib")]),
        ),
    ]

    gazebo = OpaqueFunction(function=_gazebo)
    clock = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        name="clock_bridge",
        output="screen",
        arguments=["/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock"],
    )

    # This is the official Jazzy TurtleBot 4 spawn/bridge stack. The `world`
    # launch configuration remains visible to its nested ROS-Gazebo bridges.
    spawn = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            str(tb4_bringup / "launch" / "turtlebot4_spawn.launch.py")
        ),
        launch_arguments={
            "world": WORLD_NAME,
            "model": "standard",
            "rviz": "false",
            "use_sim_time": "true",
            "localization": "false",
            "slam": "false",
            "nav2": "false",
            "x": SPAWN_X,
            "y": SPAWN_Y,
            "z": "0.0",
            "yaw": "0.0",
        }.items(),
    )

    localization = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            str(tb4_navigation / "launch" / "localization.launch.py")
        ),
        launch_arguments={
            "use_sim_time": "true",
            "map": str(package / "maps" / "furnished_house" / "map.yaml"),
            "params": str(package / "config" / "localization.yaml"),
        }.items(),
    )
    nav2 = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            str(tb4_navigation / "launch" / "nav2.launch.py")
        ),
        launch_arguments={
            "use_sim_time": "true",
            "params_file": str(tb4_navigation / "config" / "nav2.yaml"),
        }.items(),
    )

    # The simulator publishes raw OAK-D RGB. The physical bridge consumes JPEG,
    # so compress here and keep the exact same model-facing camera contract.
    camera_compressor = Node(
        package="image_transport",
        executable="republish",
        name="oakd_jpeg_republisher",
        remappings=[
            ("in", "/oakd/rgb/preview/image_raw"),
            (
                "out/compressed",
                "/oakd/rgb/preview/image_raw/compressed",
            ),
        ],
        parameters=[
            {
                "use_sim_time": True,
                "in_transport": "raw",
                "out_transport": "compressed",
            }
        ],
        output="screen",
    )
    # The bundled Lichtblick layout is shared with the physical console, whose
    # Image panel names the topic the robot-side Orin relay publishes. The
    # simulator has no Orin, so without this the browser's camera panel reads
    # "Image topic does not exist" even though the OAK-D is running. Publish the
    # simulated JPEG under the same browser-facing name rather than forking the
    # layout: the model-facing contract in the bridge below keeps using
    # /oakd/rgb/preview/image_raw/compressed, exactly as the physical robot
    # does. At the OAK-D's 2 Hz this second JPEG encode costs nothing.
    browser_camera = Node(
        package="image_transport",
        executable="republish",
        name="oakd_browser_republisher",
        remappings=[
            ("in", "/oakd/rgb/preview/image_raw"),
            ("out/compressed", "/orin/oakd/preview/image_raw/compressed"),
        ],
        parameters=[
            {
                "use_sim_time": True,
                "in_transport": "raw",
                "out_transport": "compressed",
            }
        ],
        output="screen",
    )
    # The bundled Lichtblick layout's Teleop panel publishes geometry_msgs/Twist,
    # which is what the physical robot's Humble stack takes on /cmd_vel; Jazzy
    # carries TwistStamped there, so without this the panel's arrows and the
    # keyboard do nothing at all. The relay also stops the robot when a held
    # button is released, which Gazebo's DiffDrive will not do on its own.
    # It runs as two processes because one node may not subscribe to Twist and
    # publish TwistStamped on a single topic name -- see teleop_relay's
    # docstring for the full reasoning.
    teleop_capture = Node(
        package="silly_turtlebot_ros",
        executable="teleop_relay",
        name="teleop_capture",
        parameters=[{"use_sim_time": True, "mode": "capture"}],
        output="screen",
    )
    teleop_inject = Node(
        package="silly_turtlebot_ros",
        executable="teleop_relay",
        name="teleop_inject",
        parameters=[{"use_sim_time": True, "mode": "inject"}],
        output="screen",
    )

    semantic_bridge = Node(
        package="silly_turtlebot_ros",
        executable="bridge",
        name="silly_turtlebot_bridge",
        parameters=[
            {
                "use_sim_time": True,
                "waypoints_file": str(package / "config" / "waypoints.yaml"),
                "bind_host": "0.0.0.0",
                "port": 8088,
                "primary_camera_topic": "/oakd/rgb/preview/image_raw/compressed",
                "secondary_camera_topic": "",
                "tts_command": "/bin/true",
            }
        ],
        output="screen",
    )
    foxglove = Node(
        package="foxglove_bridge",
        executable="foxglove_bridge",
        name="foxglove_bridge",
        parameters=[{"port": 8765, "use_sim_time": True}],
        output="screen",
    )
    lichtblick = ExecuteProcess(
        name="lichtblick",
        cmd=[
            "python3",
            "/viz_server.py",
            "--layout",
            "/opt/lichtblick/layout.json",
            "--bridge-url",
            "ws://127.0.0.1:8765",
        ],
        output="screen",
    )

    # The imported furnished world is intentionally detailed and can take a
    # while to parse under software rendering. Bring the stack up in dependency
    # order: Gazebo -> robot sensors -> localization -> Nav2 -> HTTP bridge.
    # Lifecycle state is a stronger readiness signal than action discovery:
    # inactive Nav2 action servers are discoverable but reject every goal.
    wait_for_world = ExecuteProcess(
        name="wait_for_gazebo_world",
        cmd=[
            "bash",
            "-c",
            (
                "until gz service -l 2>/dev/null | "
                "grep -qx '/world/small_house/control'; do sleep 1; done"
            ),
        ],
        output="screen",
    )
    wait_for_robot = ExecuteProcess(
        name="wait_for_turtlebot_sensors",
        cmd=[
            "bash",
            "-c",
            (
                "until timeout 5 ros2 topic echo --once /scan "
                "sensor_msgs/msg/LaserScan >/dev/null 2>&1; do sleep 1; done; "
                "until timeout 5 ros2 topic echo --once /odom "
                "nav_msgs/msg/Odometry >/dev/null 2>&1; do sleep 1; done"
            ),
        ],
        output="screen",
    )
    wait_for_localization = ExecuteProcess(
        name="wait_for_localization",
        cmd=[
            "bash",
            "-c",
            (
                "until ros2 lifecycle get /amcl 2>/dev/null | "
                "grep -q '^active '; do sleep 1; done"
            ),
        ],
        output="screen",
    )
    wait_for_nav2 = ExecuteProcess(
        name="wait_for_nav2",
        cmd=[
            "bash",
            "-c",
            (
                "until ros2 lifecycle get /behavior_server 2>/dev/null | "
                "grep -q '^active '; do sleep 1; done"
            ),
        ],
        output="screen",
    )
    spawn_when_world_ready = RegisterEventHandler(
        OnProcessExit(
            target_action=wait_for_world,
            on_exit=[spawn, wait_for_robot],
        )
    )
    start_localization_when_robot_ready = RegisterEventHandler(
        OnProcessExit(
            target_action=wait_for_robot,
            on_exit=[localization, camera_compressor, browser_camera,
                     wait_for_localization],
        )
    )
    start_nav2_when_localized = RegisterEventHandler(
        OnProcessExit(
            target_action=wait_for_localization,
            on_exit=[nav2, wait_for_nav2],
        )
    )
    start_bridge_when_nav2_ready = RegisterEventHandler(
        OnProcessExit(
            target_action=wait_for_nav2,
            on_exit=[semantic_bridge, teleop_capture, teleop_inject],
        )
    )

    return LaunchDescription(
        [
            *resources,
            foxglove,
            lichtblick,
            gazebo,
            clock,
            spawn_when_world_ready,
            start_localization_when_robot_ready,
            start_nav2_when_localized,
            start_bridge_when_nav2_ready,
            wait_for_world,
        ]
    )
