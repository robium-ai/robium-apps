# syntax=docker/dockerfile:1

# Reuse the same pinned web build as robot-navigation. The bundle is static
# JavaScript/Wasm, so it is safe to copy from the amd64 image on arm64 hosts.
FROM --platform=linux/amd64 ghcr.io/lichtblick-suite/lichtblick@sha256:e29673ab12265fe84a62fed0835606d8789168fe9b3395a2997d97f002ed1e9d AS lichtblick

FROM node:22-bookworm-slim AS controls
WORKDIR /extension
COPY silly-turtlebot/lichtblick-extension/package.json silly-turtlebot/lichtblick-extension/package-lock.json ./
RUN npm ci
COPY silly-turtlebot/lichtblick-extension/ ./
RUN npm run package

FROM ros:jazzy-ros-base-noble

ENV ROS_DISTRO=jazzy

# Jazzy pairs with Gazebo Harmonic. Keep the complete simulated robot, Nav2,
# image compression, and the HTTP bridge in one container so DDS discovery
# never has to cross Docker Desktop's VM boundary.
RUN apt-get update && apt-get install -y --no-install-recommends \
      ros-jazzy-turtlebot4-simulator \
      ros-jazzy-irobot-create-nodes \
      ros-jazzy-navigation2 \
      ros-jazzy-nav2-bringup \
      ros-jazzy-gz-ros2-control \
      ros-jazzy-image-transport-plugins \
      python3-colcon-common-extensions \
      python3-yaml \
      curl \
    && rm -rf /var/lib/apt/lists/*

# Keep visualization separate from the expensive simulator layer so dashboard
# changes and mirror retries do not reinstall the full TurtleBot stack.
RUN apt-get -o Acquire::Retries=3 -o Acquire::http::Timeout=20 update \
 && apt-get -o Acquire::Retries=3 -o Acquire::http::Timeout=20 install -y --no-install-recommends \
      ros-jazzy-foxglove-bridge \
    && rm -rf /var/lib/apt/lists/*

# The Jazzy Create 3 description still hard-codes Ogre 1 for its model-scoped
# Sensors system. Use Ogre2 so RGB-D and lidar rendering work without X11; the
# world must not add a second Sensors system because the robot already owns it.
RUN sed -i \
      's#<render_engine>ogre</render_engine>#<render_engine>ogre2</render_engine>#' \
      /opt/ros/${ROS_DISTRO}/share/irobot_create_description/urdf/create3.urdf.xacro \
 && grep -q '<render_engine>ogre2</render_engine>' \
      /opt/ros/${ROS_DISTRO}/share/irobot_create_description/urdf/create3.urdf.xacro

WORKDIR /ws
COPY silly-turtlebot/robot/ros_ws/src ./src
COPY silly-turtlebot/simulation/ros_ws/src ./src

# Reuse the same pinned, checksummed furnished-home asset as robot-navigation.
COPY shared/assets /opt/robium/asset-catalog
RUN python3 /opt/robium/asset-catalog/scripts/fetch_assets.py \
      --catalog /opt/robium/asset-catalog/catalog.yaml \
      --destination /opt/robium/assets/world.aws-small-house \
      world.aws-small-house

# rosdep before build, every time. The two overlays are the simulator bringup
# and the same semantic ROS bridge that is deployed to the physical robot.
RUN . /opt/ros/${ROS_DISTRO}/setup.sh \
 && apt-get update \
 && rosdep update --rosdistro ${ROS_DISTRO} \
 && rosdep install --from-paths src -y --ignore-src --skip-keys ament_python \
 && colcon build --symlink-install \
 && rm -rf /var/lib/apt/lists/*

COPY silly-turtlebot/simulation/entrypoint.sh /entrypoint.sh
COPY silly-turtlebot/simulation/smoke.sh /sim-smoke.sh
COPY silly-turtlebot/simulation/viz_server.py /viz_server.py
COPY silly-turtlebot/simulation/bundle_extension.py /bundle_extension.py
COPY --from=lichtblick /src /opt/lichtblick
COPY silly-turtlebot/viewer/patch_lichtblick_publish.py /patch_lichtblick_publish.py
RUN python3 /patch_lichtblick_publish.py
COPY silly-turtlebot/lichtblick/layout.json /opt/lichtblick/layout.json
COPY --from=controls /extension/robium.silly-turtlebot-controls-0.1.0.foxe /opt/lichtblick/robium/dashboard.foxe
COPY silly-turtlebot/lichtblick-extension/package.json /opt/lichtblick/robium/package.json
COPY silly-turtlebot/lichtblick-extension/README.md /opt/lichtblick/robium/README.md
COPY silly-turtlebot/lichtblick-extension/CHANGELOG.md /opt/lichtblick/robium/CHANGELOG.md
COPY shared/lichtblick-dashboard/deploy/preinstall-extension.mjs /opt/lichtblick/robium/preinstall-extension.mjs
RUN python3 /bundle_extension.py \
      /opt/lichtblick/index.html /opt/lichtblick/robium/dashboard.foxe
RUN cp /opt/lichtblick/index.html /opt/lichtblick/index.template.html \
 && chmod +x /entrypoint.sh /sim-smoke.sh /viz_server.py /bundle_extension.py

EXPOSE 8080 8088 8765
ENTRYPOINT ["/entrypoint.sh"]
CMD ["ros2", "launch", "silly_turtlebot_sim", "home.launch.py"]
