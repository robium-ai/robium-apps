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
      ros-jazzy-turtlebot3-gazebo \
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

# Make TurtleBot 4's upstream sensors affordable under software rendering by
# reducing only their rates. Optics, samples, ranges, noise, and frame IDs are
# preserved, so every downstream contract -- topic names, message shapes,
# Nav2's costmaps, AMCL's likelihood field -- is unchanged.
#
# This robot is far heavier than robot-navigation's Waffle Pi: it carries
# THIRTEEN render-based sensors. The rplidar, seven IR-intensity sensors and
# four cliff sensors are all `gpu_lidar` at 62 Hz upstream, and the OAK-D is an
# `rgbd_camera` that renders colour and depth. That is ~800 full ogre2 passes
# over the ~100-model house per simulated second, on llvmpipe, for a robot
# driving across a flat floor. Measured real-time factor before this work was
# 0.079 -- the simulation ran about thirteen times slower than the wall clock,
# so a robot commanded to 0.3 m/s appeared to crawl at 2 cm/s.
#
# Rate is the lever, because a render pass costs scene traversal rather than
# rasterization; the OAK-D is already only 320x240 and shrinking it further
# buys nothing. Measured here, at the 4 ms physics step that home.launch.py's
# _tune_physics() sets (10 CPUs, headless ogre2/llvmpipe, Nav2 up and idle):
#
#   camera   IR/cliff   RTF
#   30 Hz      62 Hz    0.079   <- upstream, with the 62 Hz lidar and 1 ms step
#    4 Hz      10 Hz    0.659
#    4 Hz       2 Hz    0.742
#    2 Hz      10 Hz    0.764
#    2 Hz       5 Hz    0.852   <- shipped
#    1 Hz       2 Hz    1.038
#
# Those rows are a comparative sweep taken on one repeatedly restarted
# container, so read them against each other rather than as absolutes. The
# shipped configuration measured 0.996 and 0.977 over two clean 60 s windows of
# a fresh `./app run`, at 541% CPU with Nav2 active -- effectively real time.
#
# The camera is the single dominant cost: holding IR/cliff at 2 Hz, moving the
# OAK-D from 4 Hz to 1 Hz was worth 0.742 -> 1.038 on its own. The shipped row
# stops at 2 Hz rather than taking that last step because a 1 FPS panel reads
# as a stalled camera to whoever is watching the demo.
#
# Each rate has a downstream reason rather than being a shaved number:
#   - rplidar 5 Hz: the Nav2 local costmap in turtlebot4_navigation's nav2.yaml
#     updates at 5 Hz and the global costmap at 1 Hz, so nothing consumes scans
#     faster. AMCL updates on movement, not on a clock.
#   - OAK-D 2 Hz: the agent already samples fresh frames at no more than 1 FPS
#     (see live_agent.py), so 2 Hz is twice what the model can consume and the
#     browser panel still visibly updates.
#   - cliff and IR intensity 5 Hz: same 5 Hz as the local costmap that actually
#     does this demo's obstacle avoidance. The simulated house has no cliffs at
#     all, and the 360-degree lidar already sees everything the 10-degree IR
#     cones do. They stay live rather than being deleted so the hazard topics
#     the Create 3 bridges and Nav2 expect keep publishing.
#
# This layer sits after the colcon build on purpose: re-tuning a rate is then a
# seconds-long rebuild instead of a full workspace and asset rebuild.
RUN python3 - <<'PYEOF'
from pathlib import Path

SHARE = Path('/opt/ros/jazzy/share')
EDITS = (
    ('turtlebot4_description/urdf/sensors/oakd.urdf.xacro',
     '<update_rate>30</update_rate>', '<update_rate>2</update_rate>',
     'OAK-D rgbd_camera'),
    ('turtlebot4_description/urdf/sensors/rplidar.urdf.xacro',
     'update_rate="62.0"', 'update_rate="5.0"', 'rplidar gpu_lidar'),
    ('irobot_create_description/urdf/sensors/cliff_sensor.urdf.xacro',
     '<xacro:property name="update_rate"         value="62"/>',
     '<xacro:property name="update_rate"         value="5"/>',
     'cliff sensors (x4)'),
    ('irobot_create_description/urdf/sensors/ir_intensity.urdf.xacro',
     'update_rate:=62.0', 'update_rate:=5.0', 'IR intensity sensors (x7)'),
)

# The lite profile's TurtleBot 3 Waffle Pi has only TWO render-based sensors,
# which buys back enough budget to run the camera at twice the TurtleBot 4
# profile's rate. Measured in this world at the same 4 ms step, with Nav2 up:
#
#   robot   camera             RTF     CPU
#   TB4     2 Hz (320x240)     0.99    541%
#   TB3     2 Hz (640x480)     1.065   346%   <- same rate, apples to apples
#   TB3     4 Hz (640x480)     0.956          <- shipped
#   TB3    10 Hz (640x480)     0.595
#   TB3    10 Hz (320x240)     0.647
#
# The last two rows are why the resolution is left at its upstream 640x480:
# cutting the pixel count by four bought 5%, because a render pass costs scene
# traversal over the ~100-model house rather than rasterization. Rate is the
# lever on both robots. Note also that TB3's win shows up as CPU headroom more
# than as RTF -- at an equal 2 Hz it does the same work for a third less CPU,
# which is what leaves room for the faster camera.
#
# The lidar matches the 5 Hz Nav2 local costmap exactly as the TurtleBot 4's
# does.
TB3_EDITS = (
    ('turtlebot3_gazebo/models/turtlebot3_waffle_pi/model.sdf',
     'camera', '30', '4', 'Waffle Pi camera'),
    ('turtlebot3_gazebo/models/turtlebot3_waffle_pi/model.sdf',
     'gpu_lidar', '10', '5', 'Waffle Pi lidar'),
)

for relative, upstream, wanted, label in EDITS:
    path = SHARE / relative
    text = path.read_text()
    assert text.count(upstream) == 1, (
        f'{relative}: expected exactly one occurrence of {upstream!r}, '
        f'found {text.count(upstream)}; upstream changed, re-verify')
    path.write_text(text.replace(upstream, wanted))
    print(f'{label}: {upstream} -> {wanted}')

# The Waffle Pi's rates live in SDF rather than xacro, so edit the parsed tree:
# a bare '30' would match far more than the camera's update_rate.
import xml.etree.ElementTree as ET

for relative, kind, upstream, wanted, label in TB3_EDITS:
    path = SHARE / relative
    tree = ET.parse(path)
    found = [s for s in tree.getroot().findall('.//sensor')
             if s.get('type') == kind]
    assert len(found) == 1, (
        f'{relative}: expected one {kind} sensor, found {len(found)};'
        ' upstream changed, re-verify')
    rate = found[0].find('update_rate')
    assert rate is not None and rate.text == upstream, (
        f'{relative}: {kind} update_rate is'
        f' {rate.text if rate is not None else None}, expected {upstream};'
        ' upstream changed, re-verify')
    rate.text = wanted
    tree.write(path, encoding='unicode')
    print(f'{label}: {upstream}Hz -> {wanted}Hz')
PYEOF

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
      /opt/lichtblick/index.html /opt/lichtblick/robium/dashboard.foxe \
      /opt/lichtblick/layout.json
RUN cp /opt/lichtblick/index.html /opt/lichtblick/index.template.html \
 && chmod +x /entrypoint.sh /sim-smoke.sh /viz_server.py /bundle_extension.py

EXPOSE 8080 8088 8765
ENTRYPOINT ["/entrypoint.sh"]
CMD ["ros2", "launch", "silly_turtlebot_sim", "home.launch.py"]
