# Furnished House Simulation Design

## Outcome

Replace the unreliable makerspet Living Room choice with a furnished, multi-room house based on AWS RoboMaker Small House. Keep TurtleBot3 House and the two industrial worlds unchanged.

## Asset and licensing

- Source: `aws-robotics/aws-robomaker-small-house-world`, ROS 2 branch commit `ff9631ca6d1db9c1ba656498151464b5ab74aafe`.
- License: MIT.
- The 82 MB model tree is fetched into the Docker image at the pinned revision rather than committed to this repository.
- The image retains the upstream license and commit metadata beside the asset.

## Runtime design

- Dashboard value: `furnished_house`; label: `Furnished House`.
- A local prepared world uses the pinned AWS geometry and models, with modern Gazebo Harmonic system plugins added explicitly.
- The resource path includes the pinned AWS model directory.
- Restarting the world returns navigation to `IDLE`; maps remain grouped under `/ws/maps/furnished_house/`.
- The old `living_room` option is removed. Existing files under `maps/living_room/` are preserved and not migrated automatically.

## Acceptance

- The panel offers Furnished House instead of Living Room.
- The world loads without fatal Gazebo errors.
- TurtleBot spawns in collision-free interior space.
- `/scan`, `/camera/image_raw`, `/odom`, and `/clock` produce data.
- WASD motion changes odometry.
- Start Mapping publishes `/map`; Stop Mapping saves a world-specific map and returns to `IDLE`.

