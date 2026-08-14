"""Gazebo server + optional native GUI + TurtleBot3 burger_cam + ROS bridge.

Path B composition (Task 3 Step 1 evidence): upstream
turtlebot3_world.launch.py hardcodes a gz GUI client and non-overridable
server gz_args, so we include ros_gz_sim's gz_sim.launch.py ourselves with
`-s -r --headless-rendering` and reuse the upstream sub-launch files:
- spawn_turtlebot3.launch.py: spawns the model AND starts the ros_gz
  parameter_bridge (params/turtlebot3_burger_cam_bridge.yaml: /clock, /odom,
  /tf, /cmd_vel, /imu, /scan, /joint_states, /camera/camera_info). For any
  model other than plain burger it also starts ros_gz_image's image_bridge,
  which is what puts the robot's /camera/image_raw on ROS.
- robot_state_publisher.launch.py: rsp with the TB3 urdf.
Plus foxglove_bridge on :8765. Everything runs with use_sim_time.
Tasks 5/6 IncludeLaunchDescription this file.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import AppendEnvironmentVariable
from launch.actions import DeclareLaunchArgument
from launch.actions import ExecuteProcess
from launch.actions import IncludeLaunchDescription
from launch.actions import OpaqueFunction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


FUEL_ROOT = 'https://fuel.gazebosim.org/1.0'


def world_spec(bringup, tb3_gazebo, world_name):
    """Resolve a world and a collision-free TurtleBot spawn pose."""
    if world_name == 'house':
        return (os.path.join(bringup, 'worlds', 'turtlebot3_house.world'),
                '-2.0', '-0.5')
    if world_name == 'arena':
        return (os.path.join(tb3_gazebo, 'worlds', 'turtlebot3_world.world'),
                '-2.0', '-0.5')
    if world_name == 'tugbot_warehouse':
        return (f'{FUEL_ROOT}/OpenRobotics/worlds/'
                'Tugbot%20in%20Warehouse/2', '0.0', '0.0')
    if world_name == 'industrial_warehouse':
        return (f'{FUEL_ROOT}/OpenRobotics/worlds/'
                'industrial-warehouse/4', '0.0', '0.0')
    if world_name == 'living_room':
        return (f'{FUEL_ROOT}/makerspet/worlds/living_room/1', '1.8', '-1.8')
    raise ValueError(f'unknown simulation world: {world_name}')


def gazebo_actions(context, bringup, tb3_gazebo, ros_gz_sim):
    """Create one server and, for native mode, one attached GUI client."""
    gui_value = LaunchConfiguration('gui').perform(context).lower()
    if gui_value not in ('true', 'false'):
        raise ValueError('gui must be true or false')
    world, _x, _y = world_spec(
        bringup, tb3_gazebo,
        LaunchConfiguration('world').perform(context).lower())
    server_flags = ('-r -s -v2 ' if gui_value == 'true'
                    else '-r -s --headless-rendering -v2 ')
    actions = [IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(ros_gz_sim, 'launch', 'gz_sim.launch.py')),
        launch_arguments={
            'gz_args': [server_flags, world],
            'on_exit_shutdown': 'true',
        }.items(),
    )]
    if gui_value == 'true':
        actions.append(ExecuteProcess(
            cmd=['gz', 'sim', '-g'], output='screen'))
    return actions


def robot_actions(context, bringup, tb3_gazebo):
    """Spawn the existing TurtleBot in free space for the selected world."""
    _world, x_pose, y_pose = world_spec(
        bringup, tb3_gazebo,
        LaunchConfiguration('world').perform(context).lower())
    return [IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(tb3_gazebo, 'launch', 'spawn_turtlebot3.launch.py')),
        launch_arguments={'x_pose': x_pose, 'y_pose': y_pose}.items(),
    )]


def generate_launch_description():
    tb3_gazebo = get_package_share_directory('turtlebot3_gazebo')
    ros_gz_sim = get_package_share_directory('ros_gz_sim')
    bringup = get_package_share_directory('indoor_nav_bringup')

    # The house is the default environment: a ~15 x 10.6 m multi-room floor
    # plan with doorways and furniture, so the SLAM/Nav2 run reads as indoor
    # navigation rather than a lap around an arena of pillars. Both worlds are
    # shipped by turtlebot3_gazebo and are byte-for-byte identical apart from
    # the model they include (plus `<shadows>0</shadows>`, which the house
    # adds and which is cheaper, not costlier) — same ODE physics, same
    # plugins, same two Fuel includes. The arena stays selectable as
    # `world:=arena`: every camera and lidar frame here is software-rendered
    # (llvmpipe, no GPU), so a one-flag fallback to the cheap scene is what
    # lets a real-time-factor regression be bisected against the world.
    world_arg = DeclareLaunchArgument(
        'world', default_value='house',
        choices=['house', 'arena', 'tugbot_warehouse',
                 'industrial_warehouse', 'living_room'],
        description='local or pinned Gazebo Fuel environment')
    gui_arg = DeclareLaunchArgument(
        'gui', default_value='false', choices=['true', 'false'],
        description='open a native Gazebo GUI attached to the server')

    set_resource_path = AppendEnvironmentVariable(
        'GZ_SIM_RESOURCE_PATH', os.path.join(tb3_gazebo, 'models'))
    gazebo = OpaqueFunction(
        function=gazebo_actions, args=[bringup, tb3_gazebo, ros_gz_sim])

    # Spawns TURTLEBOT3_MODEL (burger_cam via container env) and starts the
    # ros_gz parameter_bridge from turtlebot3_burger_cam_bridge.yaml. That
    # launch also starts ros_gz_image's image_bridge for any model other than
    # plain burger, which is what puts /camera/image_raw on ROS for us.
    # (-2.0, -0.5) is upstream's default spawn for BOTH turtlebot3_world.launch.py
    # and turtlebot3_house.launch.py, and it lands in interior free space in the
    # house (verified against the model's collision geometry at the lidar plane),
    # so the world swap does not move the robot. That matters downstream: the
    # saved map's origin is the SLAM start pose, so `map = world + (2.0, 0.5)`
    # still holds and every frame-conversion comment stays true.
    spawn = OpaqueFunction(
        function=robot_actions, args=[bringup, tb3_gazebo])

    rsp = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(tb3_gazebo, 'launch',
                         'robot_state_publisher.launch.py')),
        launch_arguments={'use_sim_time': 'true'}.items(),
    )

    # Port is a launch arg so the demo scenario can move the bridge behind
    # its gateway (demo: 8766 internal); every other scenario keeps 8765.
    bridge_port = DeclareLaunchArgument('bridge_port', default_value='8765')
    bridge_arg = DeclareLaunchArgument(
        'bridge', default_value='true', choices=['true', 'false'],
        description='start foxglove_bridge (false under session_manager)')
    foxglove = Node(
        package='foxglove_bridge', executable='foxglove_bridge',
        condition=IfCondition(LaunchConfiguration('bridge')),
        parameters=[{
            'port': LaunchConfiguration('bridge_port'),
            'use_sim_time': True,
        }],
        output='screen',
    )

    return LaunchDescription([
        world_arg,
        gui_arg,
        bridge_port,
        bridge_arg,
        set_resource_path,
        gazebo,
        spawn,
        rsp,
        foxglove,
    ])
