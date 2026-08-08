"""Headless sim bringup: gz server (software rendering) + TB3 burger + bridge.

Path B composition (Task 3 Step 1 evidence): upstream
turtlebot3_world.launch.py hardcodes a gz GUI client and non-overridable
server gz_args, so we include ros_gz_sim's gz_sim.launch.py ourselves with
`-s -r --headless-rendering` and reuse the upstream sub-launch files:
- spawn_turtlebot3.launch.py: spawns the model AND starts the ros_gz
  parameter_bridge (params/turtlebot3_burger_cam_bridge.yaml: /clock, /odom,
  /tf, /cmd_vel, /imu, /scan, /joint_states, /camera/camera_info). For any
  model other than plain burger it also starts ros_gz_image's image_bridge,
  which is what puts the robot's /camera/image_raw on ROS.
Plus a static overhead_camera model (our own, spawned separately) with its
own image_bridge for /overhead/image_raw — the arena view.
- robot_state_publisher.launch.py: rsp with the TB3 urdf.
Plus foxglove_bridge on :8765. Everything runs with use_sim_time.
Tasks 5/6 IncludeLaunchDescription this file.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import AppendEnvironmentVariable
from launch.actions import DeclareLaunchArgument
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    tb3_gazebo = get_package_share_directory('turtlebot3_gazebo')
    ros_gz_sim = get_package_share_directory('ros_gz_sim')
    bringup = get_package_share_directory('indoor_nav_bringup')

    world = os.path.join(tb3_gazebo, 'worlds', 'turtlebot3_world.world')

    set_resource_path = AppendEnvironmentVariable(
        'GZ_SIM_RESOURCE_PATH', os.path.join(tb3_gazebo, 'models'))
    # Our own models (overhead_camera) resolve via model:// the same way.
    set_own_resource_path = AppendEnvironmentVariable(
        'GZ_SIM_RESOURCE_PATH', os.path.join(bringup, 'models'))

    # Server only (-s), running (-r), software rendering for the gpu_lidar
    # in a GPU-less/headless container (R1).
    gzserver = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(ros_gz_sim, 'launch', 'gz_sim.launch.py')),
        launch_arguments={
            'gz_args': ['-r -s --headless-rendering -v2 ', world],
            'on_exit_shutdown': 'true',
        }.items(),
    )

    # Spawns TURTLEBOT3_MODEL (burger_cam via container env) and starts the
    # ros_gz parameter_bridge from turtlebot3_burger_cam_bridge.yaml. That
    # launch also starts ros_gz_image's image_bridge for any model other than
    # plain burger, which is what puts /camera/image_raw on ROS for us.
    spawn = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(tb3_gazebo, 'launch', 'spawn_turtlebot3.launch.py')),
        launch_arguments={'x_pose': '-2.0', 'y_pose': '-0.5'}.items(),
    )

    # Static overhead view of the arena. Spawned as its own model rather than
    # baked into the world so the upstream turtlebot3_world.world stays
    # untouched.
    overhead = Node(
        package='ros_gz_sim', executable='create',
        arguments=['-name', 'overhead_camera', '-file',
                   os.path.join(bringup, 'models', 'overhead_camera',
                                'model.sdf')],
        output='screen',
    )

    # The parameter_bridge carries camera_info; images go over image_bridge,
    # which transports them far more cheaply.
    overhead_image_bridge = Node(
        package='ros_gz_image', executable='image_bridge',
        arguments=['overhead/image_raw'],
        parameters=[{'use_sim_time': True}],
        output='screen',
    )

    rsp = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(tb3_gazebo, 'launch',
                         'robot_state_publisher.launch.py')),
        launch_arguments={'use_sim_time': 'true'}.items(),
    )

    # Port is a launch arg so the demo scenario can move the bridge behind
    # its gateway (demo: 8766 internal); every other scenario keeps 8765.
    bridge_port = DeclareLaunchArgument('bridge_port', default_value='8765')
    foxglove = Node(
        package='foxglove_bridge', executable='foxglove_bridge',
        parameters=[{
            'port': LaunchConfiguration('bridge_port'),
            'use_sim_time': True,
        }],
        output='screen',
    )

    return LaunchDescription([
        bridge_port,
        set_resource_path,
        set_own_resource_path,
        gzserver,
        spawn,
        overhead,
        overhead_image_bridge,
        rsp,
        foxglove,
    ])
