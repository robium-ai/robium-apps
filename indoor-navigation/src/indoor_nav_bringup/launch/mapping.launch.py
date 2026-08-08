"""Interactive mapping/localization dashboard: SLAM + Nav2 + browser controls.

One stack, two session modes, chosen at launch:

  mode:=mapping        slam_toolbox builds a map. Save writes it and KEEPS
                       mapping. Load is refused (nothing to load into).
  mode:=localization   map_server + AMCL localize on the saved .pgm. No
                       slam_toolbox at all. Save is refused; Load switches map.

`mode` is a launch argument rather than a button because the two modes are
genuinely different node sets, not a parameter flip — one has slam_toolbox and
no AMCL, the other the reverse. Only one of them can own map->odom, so they
cannot coexist and no button can transition between them.

Nav2 runs in BOTH modes, which is what makes navigation need no button: /map
and map->odom exist either way (slam_toolbox while mapping, map_server + AMCL
while localizing), so clicking a goal in the 3D panel works as soon as the
stack is up.

Teleop and Nav2 both end up publishing /cmd_vel, which sounds like a conflict
and mostly is not: Nav2's chain (controller -> velocity_smoother ->
collision_monitor) is silent unless a goal is active, so the two only overlap
if you grab the teleop while the robot is already driving itself. That reads as
"taking over", and the relay's deadman means letting go hands control back
rather than latching a velocity.

Browser wiring:
  Teleop panel -> /cmd_vel_teleop (Twist) -> teleop_relay -> /cmd_vel (Stamped)
  CallService  -> /mapping/save | /mapping/load | /mapping/reset (Trigger)
  Parameters   -> map_manager's `map_name`, which those services act on
  Indicator    -> /mapping/state, so the session mode is visible at a glance
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.actions import ExecuteProcess
from launch.actions import IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch.substitutions import PathJoinSubstitution
from launch.substitutions import PythonExpression
from launch_ros.actions import Node


def generate_launch_description():
    pkg = get_package_share_directory('indoor_nav_bringup')
    slam_toolbox = get_package_share_directory('slam_toolbox')

    # Redeclared and forwarded rather than left to sim.launch.py's default:
    # `ros2 launch` validates CLI arguments against the TOP-LEVEL launch file,
    # so `world:=arena` would be rejected here as unknown if only the included
    # file declared it.
    world_arg = DeclareLaunchArgument(
        'world', default_value='house', choices=['house', 'arena'],
        description='simulated environment: house (default) or arena')
    mode_arg = DeclareLaunchArgument(
        'mode', default_value='mapping', choices=['mapping', 'localization'],
        description='session mode: build a map, or localize on a saved one')
    map_name_arg = DeclareLaunchArgument(
        'map_name', default_value='map',
        description='initial map name; editable live from the Parameters panel')

    mode = LaunchConfiguration('mode')

    is_mapping = PythonExpression(["'", mode, "' == 'mapping'"])
    is_localization = PythonExpression(["'", mode, "' != 'mapping'"])
    # /ws/maps is the bind mount, so a map saved in one session is visible to
    # the next without rebuilding the image. PathJoin rather than
    # PythonExpression: the latter would eval the map name as Python source.
    map_yaml = PathJoinSubstitution(
        ['/ws/maps', [LaunchConfiguration('map_name'), '.yaml']])

    sim = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg, 'launch', 'sim.launch.py')),
        launch_arguments={'world': LaunchConfiguration('world')}.items())

    # Mapping only: slam_toolbox owns /map and map->odom here.
    slam = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(slam_toolbox, 'launch', 'online_async_launch.py')),
        condition=IfCondition(is_mapping),
        launch_arguments={
            'use_sim_time': 'true',
            'slam_params_file': os.path.join(pkg, 'config', 'slam_params.yaml'),
        }.items())

    # Localization only: map_server + AMCL take over those same two jobs.
    # Reading from /ws/maps (the bind mount) rather than the installed share
    # directory, so a map saved in one session is visible to the next without
    # rebuilding the image.
    nav2_mapping = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg, 'launch', 'nav2_servers.launch.py')),
        condition=IfCondition(is_mapping))

    nav2_localization = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg, 'launch', 'nav2_servers.launch.py')),
        condition=IfCondition(is_localization),
        launch_arguments={
            'localization': 'true',
            'map_yaml': map_yaml,
        }.items())

    relay = Node(
        package='indoor_nav_bringup', executable='teleop_relay',
        name='teleop_relay', output='screen',
        parameters=[{'use_sim_time': True}])

    manager = Node(
        package='indoor_nav_bringup', executable='map_manager',
        name='map_manager', output='screen',
        parameters=[{
            'use_sim_time': True,
            'session_mode': mode,
            'map_name': LaunchConfiguration('map_name'),
            'maps_dir': '/ws/maps',
        }])

    # Bundled viewer on :8080, foxglove_bridge on :8765 (from sim.launch.py).
    # Mounted from scripts/ by compose, so the layout and this server can be
    # edited and reloaded without an image rebuild.
    viz = ExecuteProcess(
        cmd=['python3', '/ws/scripts/viz_server.py', '--port', '8080',
             '--layout', '/opt/lichtblick/mapping-layout.json'],
        output='screen')

    return LaunchDescription([
        world_arg, mode_arg, map_name_arg,
        sim, slam, nav2_mapping, nav2_localization, relay, manager, viz,
    ])
