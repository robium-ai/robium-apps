"""Headless TurtleBot 3 Waffle Pi + Nav2 in the pinned furnished-home world.

This is the fast simulation profile. It exists because the Gemini agent needs a
robot that navigates, spins, and shows a camera -- not a faithful TurtleBot 4.
The cost difference is entirely sensor count: TurtleBot 4 carries thirteen
render-based sensors (one lidar, seven IR-intensity, four cliff, and an RGB-D
camera), while this robot carries two. Under CPU-only rendering that is the
whole simulation budget, so the lite profile buys real time back and spends
some of it on a smoother camera for the model to look through.

`home.launch.py` keeps the TurtleBot 4 stack unchanged for hardware-parity work.
Both share the same world, the same saved map, and the same waypoints: this
robot spawns at the world pose that map was made from, so its map-frame pose is
the origin, exactly as the TurtleBot 4's is.

What this profile does NOT have is the Create 3 dock. `dock`, `undock`, and
`is_docked` therefore report false through the bridge's health endpoint, which
already discovers capabilities from live action servers rather than assuming
them. Distance motion still works: the bridge falls back from the Create 3
`DriveDistance` action to Nav2's `DriveOnHeading`/`BackUp`.
"""

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
from launch_ros.parameter_descriptions import ParameterFile

from silly_turtlebot_sim.world import (
    ASSET_ROOT,
    SPAWN_X,
    SPAWN_Y,
    WORLD_NAME,
    prepare_world,
)

# TurtleBot 3 has no model-scoped Sensors system of its own, so unlike the
# TurtleBot 4 world this one must supply it or the camera and lidar never
# render at all.
SYSTEMS = (
    ("gz-sim-physics-system", "gz::sim::systems::Physics"),
    ("gz-sim-user-commands-system", "gz::sim::systems::UserCommands"),
    ("gz-sim-scene-broadcaster-system", "gz::sim::systems::SceneBroadcaster"),
    ("gz-sim-sensors-system", "gz::sim::systems::Sensors"),
    ("gz-sim-imu-system", "gz::sim::systems::Imu"),
)
PREPARED_WORLD = "small_house.silly-turtlebot-lite.world"

# Waffle Pi's pinhole camera, straight from its model.sdf: 640x480 at
# horizontal_fov 1.085595 rad. The vertical angle follows from the aspect
# ratio. The bridge hands these to Gemini so it can reason about what is
# outside the frame, so they must describe this robot, not the OAK-D.
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
CAMERA_HFOV_DEG = 62.2
CAMERA_VFOV_DEG = 48.6

RAW_CAMERA_TOPIC = "/camera/image_raw"
MODEL_CAMERA_TOPIC = "/camera/image_raw/compressed"
BROWSER_CAMERA_TOPIC = "/orin/oakd/preview/image_raw/compressed"


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
    tb3_gazebo = Path(get_package_share_directory("turtlebot3_gazebo"))

    resources = [
        AppendEnvironmentVariable("GZ_SIM_RESOURCE_PATH", str(ASSET_ROOT / "models")),
        AppendEnvironmentVariable("GZ_SIM_RESOURCE_PATH", str(tb3_gazebo / "models")),
        SetEnvironmentVariable("TURTLEBOT3_MODEL", "waffle_pi"),
    ]

    gazebo = OpaqueFunction(function=_gazebo)

    # Upstream's spawn launch also starts the ros_gz parameter_bridge for
    # /clock, /odom, /tf, /cmd_vel, /imu, /scan and /camera/camera_info, plus
    # ros_gz_image's image_bridge for /camera/image_raw (it starts that one for
    # every model except plain burger). So this single include is the whole
    # robot-to-ROS boundary; no separate clock bridge is needed here.
    spawn = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            str(tb3_gazebo / "launch" / "spawn_turtlebot3.launch.py")
        ),
        launch_arguments={"x_pose": SPAWN_X, "y_pose": SPAWN_Y}.items(),
    )

    # Upstream's TurtleBot3 launch always appends "/" to frame_prefix, which
    # with its default empty prefix publishes /base_link while Gazebo publishes
    # base_footprint without a slash. Web visualizers then see two disconnected
    # TF trees and draw the robot in pieces. Start the publisher directly so
    # every frame keeps its canonical URDF name.
    urdf = tb3_gazebo / "urdf" / "turtlebot3_waffle_pi.urdf"
    robot_state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        name="robot_state_publisher",
        parameters=[
            {
                "use_sim_time": True,
                "robot_description": urdf.read_text(encoding="utf-8"),
            }
        ],
        output="screen",
    )

    # Nav2 is composed from its servers directly rather than through
    # nav2_bringup's launch files, matching robot-navigation: those files
    # expose no bond_timeout control, and this params file's
    # $(find-pkg-share ...) substitutions for the behaviour-tree XML paths need
    # ParameterFile(allow_substs=True) to expand at all.
    params = ParameterFile(str(package / "config" / "nav2_tb3.yaml"),
                           allow_substs=True)
    map_yaml = str(package / "maps" / "furnished_house" / "map.yaml")
    remappings = [("/tf", "tf"), ("/tf_static", "tf_static")]

    def server(pkg_name, executable, name, extra_remaps=(), extra_params=()):
        return Node(
            package=pkg_name,
            executable=executable,
            name=name,
            output="screen",
            respawn=True,
            respawn_delay=2.0,
            parameters=[params] + list(extra_params),
            remappings=remappings + list(extra_remaps),
        )

    # The params file ships a relative `yaml_filename`, which would resolve
    # against each node's working directory. Override it with the installed
    # absolute path.
    nav2 = [
        server("nav2_map_server", "map_server", "map_server",
               extra_params=[{"yaml_filename": map_yaml}]),
        server("nav2_amcl", "amcl", "amcl"),
        server("nav2_controller", "controller_server", "controller_server",
               [("cmd_vel", "cmd_vel_nav")]),
        server("nav2_smoother", "smoother_server", "smoother_server"),
        server("nav2_planner", "planner_server", "planner_server"),
        server("nav2_behaviors", "behavior_server", "behavior_server",
               [("cmd_vel", "cmd_vel_nav")]),
        server("nav2_bt_navigator", "bt_navigator", "bt_navigator"),
        server("nav2_waypoint_follower", "waypoint_follower",
               "waypoint_follower"),
        server("nav2_velocity_smoother", "velocity_smoother",
               "velocity_smoother", [("cmd_vel", "cmd_vel_nav")]),
        server("nav2_collision_monitor", "collision_monitor",
               "collision_monitor"),
    ]

    # map_server and amcl lead so the map exists and the robot is localized
    # before the costmaps and planner activate.
    MANAGED_NODES = [
        "map_server",
        "amcl",
        "controller_server",
        "smoother_server",
        "planner_server",
        "behavior_server",
        "velocity_smoother",
        "collision_monitor",
        "bt_navigator",
        "waypoint_follower",
    ]

    lifecycle_manager = Node(
        package="nav2_lifecycle_manager",
        executable="lifecycle_manager",
        name="lifecycle_manager_navigation",
        output="screen",
        parameters=[
            {
                "use_sim_time": True,
                "autostart": True,
                "bond_timeout": 0.0,
                "node_names": MANAGED_NODES,
            }
        ],
    )

    # The manager starts configuring roughly a second after it comes up, and it
    # does not retry a change_state call that times out -- one slow server and
    # the whole bringup stalls half-configured, with the later servers left
    # unconfigured and every Nav2 goal rejected. Constructing ten servers while
    # Gazebo is still settling the furnished world is easily slow enough to hit
    # that. Jazzy's lifecycle manager exposes no service timeout to widen, so
    # hold it until every server is actually answering, which is the condition
    # it needs rather than a delay guessed against one machine's speed.
    wait_for_nav2_services = ExecuteProcess(
        name="wait_for_nav2_services",
        cmd=[
            "bash",
            "-c",
            "until "
            + " && ".join(
                f"ros2 service type /{node}/change_state >/dev/null 2>&1"
                for node in MANAGED_NODES
            )
            + "; do sleep 1; done",
        ],
        output="screen",
    )

    # The simulator publishes raw RGB. The physical bridge consumes JPEG, so
    # compress here and keep the exact same model-facing camera contract.
    camera_compressor = Node(
        package="image_transport",
        executable="republish",
        name="camera_jpeg_republisher",
        remappings=[
            ("in", RAW_CAMERA_TOPIC),
            ("out/compressed", MODEL_CAMERA_TOPIC),
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

    # Same reason as the TurtleBot 4 profile: the bundled Lichtblick layout is
    # shared with the physical console, whose Image panel names the topic the
    # robot-side Orin relay publishes. Publish under that browser-facing name
    # so one layout serves every profile.
    browser_camera = Node(
        package="image_transport",
        executable="republish",
        name="oakd_browser_republisher",
        remappings=[
            ("in", RAW_CAMERA_TOPIC),
            ("out/compressed", BROWSER_CAMERA_TOPIC),
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
                "primary_camera_topic": MODEL_CAMERA_TOPIC,
                "secondary_camera_topic": "",
                "tts_command": "/bin/true",
                "camera_width": CAMERA_WIDTH,
                "camera_height": CAMERA_HEIGHT,
                "camera_horizontal_fov_deg": CAMERA_HFOV_DEG,
                "camera_vertical_fov_deg": CAMERA_VFOV_DEG,
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

    # Same dependency-ordered bringup as the TurtleBot 4 profile, for the same
    # reason: the furnished world is slow to parse under software rendering,
    # and lifecycle state is a stronger readiness signal than action discovery
    # because inactive Nav2 servers are discoverable but reject every goal.
    wait_for_world = ExecuteProcess(
        name="wait_for_gazebo_world",
        cmd=[
            "bash",
            "-c",
            (
                f"until gz service -l 2>/dev/null | "
                f"grep -qx '/world/{WORLD_NAME}/control'; do sleep 1; done"
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
            on_exit=[spawn, robot_state_publisher, wait_for_robot],
        )
    )
    start_nav2_when_robot_ready = RegisterEventHandler(
        OnProcessExit(
            target_action=wait_for_robot,
            on_exit=[
                *nav2,
                camera_compressor,
                browser_camera,
                wait_for_nav2_services,
            ],
        )
    )
    manage_nav2_when_servers_answer = RegisterEventHandler(
        OnProcessExit(
            target_action=wait_for_nav2_services,
            on_exit=[lifecycle_manager, wait_for_nav2],
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
            spawn_when_world_ready,
            start_nav2_when_robot_ready,
            manage_nav2_when_servers_answer,
            start_bridge_when_nav2_ready,
            wait_for_world,
        ]
    )
