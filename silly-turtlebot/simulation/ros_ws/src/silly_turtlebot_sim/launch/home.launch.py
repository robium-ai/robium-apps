"""Headless TurtleBot 4 + Nav2 in the pinned furnished-home environment."""

import os
import re
import xml.etree.ElementTree as ET
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

ASSET_ROOT = Path("/opt/robium/assets/world.aws-small-house")
SOURCE_WORLD = ASSET_ROOT / "worlds" / "small_house.world"
WORLD_NAME = "small_house"
SPAWN_X = "3.5"
SPAWN_Y = "1.0"
SYSTEMS = (
    ("gz-sim-physics-system", "gz::sim::systems::Physics"),
    ("gz-sim-user-commands-system", "gz::sim::systems::UserCommands"),
    ("gz-sim-scene-broadcaster-system", "gz::sim::systems::SceneBroadcaster"),
    ("gz-sim-imu-system", "gz::sim::systems::Imu"),
)
COLLADA_TAGS_WITH_GLOBAL_NAMES = {"effect", "image", "material"}


def _namespace_collada(path: Path) -> None:
    """Make legacy material resources unique across one Ogre2 scene."""
    tree = ET.parse(path)
    root = tree.getroot()
    namespace = root.tag.partition("}")[0].removeprefix("{")
    if namespace:
        ET.register_namespace("", namespace)

    relative = path.relative_to(ASSET_ROOT / "models")
    prefix = re.sub(r"[^A-Za-z0-9_]", "_", f"{relative.parts[0]}_{path.stem}")
    renamed: dict[str, str] = {}
    for element in root.iter():
        old_id = element.get("id")
        if old_id:
            renamed[old_id] = f"{prefix}_{old_id}"

        local_tag = element.tag.rsplit("}", 1)[-1]
        old_name = element.get("name")
        if old_name and local_tag in COLLADA_TAGS_WITH_GLOBAL_NAMES:
            element.set("name", f"{prefix}_{old_name}")

    for element in root.iter():
        old_id = element.get("id")
        if old_id:
            element.set("id", renamed[old_id])
        for attribute, value in tuple(element.attrib.items()):
            if value in renamed:
                element.set(attribute, renamed[value])
            elif value.startswith("#") and value[1:] in renamed:
                element.set(attribute, f"#{renamed[value[1:]]}")
        if element.text:
            value = element.text.strip()
            if value in renamed:
                element.text = element.text.replace(value, renamed[value])
            elif value.startswith("#") and value[1:] in renamed:
                element.text = element.text.replace(value, f"#{renamed[value[1:]]}")

    tree.write(path, encoding="unicode")


def _prepare_world() -> str:
    """Repair the pinned Gazebo Classic world for modern Gazebo Harmonic."""
    if not SOURCE_WORLD.is_file():
        raise RuntimeError(f"furnished-home asset is missing: {SOURCE_WORLD}")

    root = ET.parse(SOURCE_WORLD).getroot()
    world = root.find("world")
    if world is None:
        raise RuntimeError("furnished-home asset has no <world> element")
    # The legacy file calls this world "default". Give it a stable explicit
    # name because TurtleBot 4's Gazebo bridges build sensor topic paths from it.
    world.set("name", WORLD_NAME)

    # The source asset contains a duplicate ixx field where the second entry is
    # izz. Be strict so an upstream asset change cannot silently corrupt physics.
    shoe_model = (
        ASSET_ROOT
        / "models"
        / "aws_robomaker_residential_ShoeRack_01"
        / "model.sdf"
    )
    shoe_tree = ET.parse(shoe_model)
    inertia = shoe_tree.getroot().find(".//inertia")
    if inertia is None:
        raise RuntimeError("shoe-rack model has no inertia")
    ixx = inertia.findall("ixx")
    izz = inertia.findall("izz")
    if len(ixx) == 2 and not izz:
        ixx[1].tag = "izz"
        shoe_tree.write(shoe_model, encoding="unicode")
    elif len(ixx) != 1 or len(izz) != 1:
        raise RuntimeError("shoe-rack inertia changed; re-verify the world patch")

    # Correct legacy portrait texture paths and namespace COLLADA identifiers.
    # The asset was authored for Gazebo Classic and repeats names such as
    # "Material #25" across files; Ogre2 treats those names as scene-global.
    for mesh in (ASSET_ROOT / "models").rglob("*.DAE"):
        contents = mesh.read_text(encoding="utf-8")
        corrected = contents.replace("../../../../photos/", "../../../photos/")
        if corrected != contents:
            mesh.write_text(corrected, encoding="utf-8")
        _namespace_collada(mesh)

    existing = {plugin.get("name") for plugin in world.findall("plugin")}
    for filename, name in SYSTEMS:
        if name in existing:
            continue
        ET.SubElement(world, "plugin", {"filename": filename, "name": name})

    prepared = SOURCE_WORLD.with_name("small_house.silly-turtlebot.world")
    ET.ElementTree(root).write(prepared, encoding="unicode")
    return str(prepared)


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
                    _prepare_world(),
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
            on_exit=[localization, camera_compressor, wait_for_localization],
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
            on_exit=[semantic_bridge],
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
