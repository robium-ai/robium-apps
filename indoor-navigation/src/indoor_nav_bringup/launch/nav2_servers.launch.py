"""The Nav2 server set, optionally with map_server + AMCL in front of it.

Shared by the slam, nav and mapping scenarios so they cannot drift apart.

  localization:=false   the eight navigation servers only. Something else
                        (slam_toolbox) supplies /map and map->odom.
  localization:=true    map_server + AMCL first, localizing on a saved .pgm.

Why the servers are launched DIRECTLY rather than via nav2_bringup (both
alternatives were tried live and failed):

1. bringup_launch.py with slam:=True — on jazzy its slam_launch.py starts its
   OWN slam_toolbox (online_sync) + map_saver_server + a second lifecycle
   manager, so adding online_async alongside duplicates SLAM: two map->odom
   publishers, lifecycle transition errors, bond deaths, 0/9 waypoints.
2. navigation_launch.py — correct node set, but it hard-codes the lifecycle
   manager's parameters (autostart + node_names only), so `bond_timeout`
   cannot be set. On Docker Desktop/macOS the container stalls for seconds
   under the activation load spike (gz + ceres + DWB in one VM); the default
   4 s bond timeout then declares controller_server dead and tears the stack
   down ("CRITICAL FAILURE: SERVER controller_server IS DOWN"), 0/9 again.

So: our own lifecycle manager with `bond_timeout: 0.0` (Nav2's documented
escape hatch for platforms with scheduling hiccups), and the same node set as
jazzy's navigation_launch.py minus route_server and docking_server, which this
app does not use.

Ordering matters: map_server and amcl come first in node_names so the map and
localization exist before the costmaps and planner activate.

Trade-off, stated honestly: with bonds off the lifecycle manager never notices
a server crash, and although `respawn=True` restarts the process, a respawned
lifecycle node comes back UNCONFIGURED and is never re-transitioned — so a real
crash leaves the stack permanently wedged. In the slam scenario the backstop is
SLAM_TIMEOUT in scripts/run_slam.sh. The interactive dashboard deliberately has
no timeout, so there the backstop is you noticing and running `make down`.

An OpaqueFunction builds the node list because `localization` decides how many
nodes exist and what the lifecycle manager must be told to manage — that is a
Python-level branch, and launch conditions can only include or exclude entities
that were already constructed.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterFile

# Order matters to the lifecycle manager: it transitions these in sequence.
SERVERS = [
    ('nav2_controller', 'controller_server', 'controller_server', (('cmd_vel', 'cmd_vel_nav'),)),
    ('nav2_smoother', 'smoother_server', 'smoother_server', ()),
    ('nav2_planner', 'planner_server', 'planner_server', ()),
    ('nav2_behaviors', 'behavior_server', 'behavior_server', (('cmd_vel', 'cmd_vel_nav'),)),
    ('nav2_bt_navigator', 'bt_navigator', 'bt_navigator', ()),
    ('nav2_waypoint_follower', 'waypoint_follower', 'waypoint_follower', ()),
    ('nav2_velocity_smoother', 'velocity_smoother', 'velocity_smoother',
     (('cmd_vel', 'cmd_vel_nav'),)),
    ('nav2_collision_monitor', 'collision_monitor', 'collision_monitor', ()),
]

MANAGED = [
    'controller_server',
    'smoother_server',
    'planner_server',
    'behavior_server',
    'velocity_smoother',
    'collision_monitor',
    'bt_navigator',
    'waypoint_follower',
]


def build(context, *_args, **_kwargs):
    pkg = get_package_share_directory('indoor_nav_bringup')
    localization = LaunchConfiguration('localization').perform(context) == 'true'
    map_yaml = LaunchConfiguration('map_yaml').perform(context)

    # allow_substs expands the $(find-pkg-share ...) substitutions the TB3
    # params file uses for BT xml paths (navigation_launch.py does the same via
    # RewrittenYaml; without it bt_navigator gets the literal string).
    params = ParameterFile(
        os.path.join(pkg, 'config', 'nav2_params.yaml'), allow_substs=True)
    remappings = [('/tf', 'tf'), ('/tf_static', 'tf_static')]

    def server(package, executable, name, extra_remaps=(), extra_params=()):
        return Node(
            package=package, executable=executable, name=name,
            output='screen', respawn=True, respawn_delay=2.0,
            parameters=[params] + list(extra_params),
            remappings=remappings + list(extra_remaps))

    nodes, managed = [], list(MANAGED)

    if localization:
        # nav2_params.yaml ships `yaml_filename: "map.yaml"` (relative →
        # resolved against the node's cwd → broken). Always override with an
        # absolute path.
        nodes.append(server('nav2_map_server', 'map_server', 'map_server',
                            extra_params=[{'yaml_filename': map_yaml}]))
        # AMCL publishes map->odom only once it has an initial pose, so without
        # this the robot is never localized and every goal fails. The pose is
        # (0, 0, 0) because the saved map's frame origin IS the pose the robot
        # started mapping from, and sim.launch.py always spawns at that same
        # place (-2.0, -0.5) — so map (0, 0) is exactly where the robot is on a
        # fresh run. Drag a pose estimate in the 3D panel to correct it.
        nodes.append(server('nav2_amcl', 'amcl', 'amcl', extra_params=[{
            'set_initial_pose': True,
            'initial_pose.x': 0.0,
            'initial_pose.y': 0.0,
            'initial_pose.z': 0.0,
            'initial_pose.yaw': 0.0,
        }]))
        managed = ['map_server', 'amcl'] + managed

    nodes += [server(pkg_, exe, name, extra) for pkg_, exe, name, extra in SERVERS]

    nodes.append(Node(
        package='nav2_lifecycle_manager', executable='lifecycle_manager',
        name='lifecycle_manager_navigation', output='screen',
        parameters=[{
            'use_sim_time': True,
            'autostart': True,
            'bond_timeout': 0.0,
            'node_names': managed,
        }]))
    return nodes


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument(
            'localization', default_value='false', choices=['true', 'false'],
            description='add map_server + AMCL in front of the navigation servers'),
        DeclareLaunchArgument(
            'map_yaml', default_value='/ws/maps/map.yaml',
            description='absolute path to the map yaml (localization only)'),
        OpaqueFunction(function=build),
    ])
