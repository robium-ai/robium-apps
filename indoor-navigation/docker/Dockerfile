# Lichtblick web bundle donor. Assets are arch-neutral JS/wasm, so pinning
# the platform lets arm64 hosts pull the amd64 image just to copy files.
# Web assets live at /src in this image; index.html carries the literal
# /*LICHTBLICK_SUITE_DEFAULT_LAYOUT_PLACEHOLDER*/ token for default-layout
# injection (both verified against lichtblick-suite/lichtblick@main
# Dockerfile by direct fetch, 2026-08-03).
# lichtblick :latest index digest pinned 2026-08-03
FROM --platform=linux/amd64 ghcr.io/lichtblick-suite/lichtblick@sha256:e29673ab12265fe84a62fed0835606d8789168fe9b3395a2997d97f002ed1e9d AS lichtblick

FROM ros:jazzy-ros-base-noble

ENV ROS_DISTRO=jazzy

# Nav stack + TB3 sim + SLAM + viz bridge + Gazebo Harmonic (via ros_gz).
RUN apt-get update && apt-get install -y --no-install-recommends \
      ros-jazzy-navigation2 \
      ros-jazzy-nav2-bringup \
      ros-jazzy-slam-toolbox \
      ros-jazzy-turtlebot3-gazebo \
      ros-jazzy-turtlebot3-navigation2 \
      ros-jazzy-foxglove-bridge \
      ros-jazzy-ros-gz \
      python3-colcon-common-extensions \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /ws
COPY src ./src
COPY tests ./tests
COPY scripts ./scripts

# rosdep before build, every time (ros2 skill key directive).
RUN . /opt/ros/${ROS_DISTRO}/setup.sh \
 && apt-get update \
 && rosdep update --rosdistro ${ROS_DISTRO} \
 && rosdep install --from-paths src -y --ignore-src \
 && colcon build --symlink-install \
 && rm -rf /var/lib/apt/lists/*

COPY docker/entrypoint.sh /entrypoint.sh

# Bundled viewer: the demo gateway serves /opt/lichtblick on non-API GETs.
COPY --from=lichtblick /src /opt/lichtblick
COPY lichtblick/nav-layout.json /opt/lichtblick/nav-layout.json
RUN python3 - <<'PYEOF'
from pathlib import Path
idx = Path('/opt/lichtblick/index.html')
html = idx.read_text()
token = '/*LICHTBLICK_SUITE_DEFAULT_LAYOUT_PLACEHOLDER*/'
assert token in html, 'Lichtblick default-layout placeholder missing: upstream image changed, re-verify'
layout = Path('/opt/lichtblick/nav-layout.json').read_text()
idx.write_text(html.replace(token, layout))
print('lichtblick default layout injected')
PYEOF
RUN chmod +x /entrypoint.sh /ws/scripts/*.sh 2>/dev/null || chmod +x /entrypoint.sh

ENV TURTLEBOT3_MODEL=burger
EXPOSE 8765
ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash"]
