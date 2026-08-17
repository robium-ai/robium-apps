# Waffle Pi and Two Simulation Worlds Design

## Goal

Simplify robot-navigation to one larger supported robot and two useful environments. TurtleBot3 Waffle Pi becomes the only robot. The control panel exposes only House and Warehouse, with House selected at startup.

## Environment contract

- `furnished_house` remains the internal identifier and map directory for the AWS furnished environment; its visible label becomes `House`.
- `tugbot_warehouse` remains the internal identifier and map directory for the OpenRobotics warehouse; its visible label becomes `Warehouse`.
- `house`, `arena`, and `industrial_warehouse` are removed from selectable and accepted session worlds.
- Existing maps are preserved. No map directory is renamed or migrated.

## Robot contract

- Set `TURTLEBOT3_MODEL=waffle_pi` in Docker, native launch environment, and app metadata.
- Reuse the upstream Jazzy Waffle Pi SDF, bridge YAML, and URDF supplied by `turtlebot3_gazebo`.
- Preserve the existing ROS interfaces: `/cmd_vel`, `/odom`, `/tf`, `/imu`, `/scan`, `/camera/image_raw`, and `/camera/camera_info`.
- Use the upstream Waffle Pi Nav2 robot radius of `0.15` m in both local and global costmaps.
- Keep the CPU-friendly camera rate at 10 Hz without replacing Waffle Pi's existing pinhole camera model.

## Runtime behavior

- A fresh mapping session starts Waffle Pi in House with navigation state `IDLE` and no `/map` publisher.
- Restarting into either environment returns the session to `IDLE`.
- Mapping and localization remain isolated by the unchanged internal world identifiers.
- The warehouse's upstream Tugbot remains scenery; the controllable robot is always Waffle Pi.

## Verification

- Automated tests cover the two visible options, accepted world identifiers, default world, Waffle Pi environment selection, camera optimization, and 0.15 m Nav2 radius.
- Live checks launch both House and Warehouse and verify clock, lidar, camera, odometry, teleop motion, and the mapping save/stop lifecycle.

