# syntax=docker/dockerfile:1

# Lichtblick web bundle donor. Assets are arch-neutral JS/wasm, so pinning
# the platform lets arm64 hosts pull the amd64 image just to copy files.
# Web assets live at /src in this image; index.html carries the literal
# /*LICHTBLICK_SUITE_DEFAULT_LAYOUT_PLACEHOLDER*/ token for default-layout
# injection (both verified against lichtblick-suite/lichtblick@main
# Dockerfile by direct fetch, 2026-08-03).
# lichtblick :latest index digest pinned 2026-08-03
FROM --platform=linux/amd64 ghcr.io/lichtblick-suite/lichtblick@sha256:e29673ab12265fe84a62fed0835606d8789168fe9b3395a2997d97f002ed1e9d AS lichtblick

FROM node:22-bookworm-slim AS dashboard

WORKDIR /extension
COPY shared/lichtblick-dashboard/package.json shared/lichtblick-dashboard/package-lock.json ./
RUN npm ci
COPY shared/lichtblick-dashboard/ ./
RUN npm run package

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
      ros-jazzy-teleop-twist-keyboard \
      python3-colcon-common-extensions \
      python3-yaml \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /ws
COPY robot-navigation/src ./src
COPY robot-navigation/scripts ./scripts

# Materialize only this app's declared worlds from the shared, checksummed
# catalog. Large payloads remain outside git; manifests and licenses stay in
# the image beside the resolver for provenance inspection.
COPY shared/assets /opt/robium/asset-catalog
RUN python3 /opt/robium/asset-catalog/scripts/fetch_assets.py \
      --catalog /opt/robium/asset-catalog/catalog.yaml \
      --destination /opt/robium/assets/world.aws-small-house \
      world.aws-small-house \
 && python3 /opt/robium/asset-catalog/scripts/fetch_assets.py \
      --catalog /opt/robium/asset-catalog/catalog.yaml \
      --destination /opt/robium/assets/world.tugbot-warehouse \
      world.tugbot-warehouse

# rosdep before build, every time (ros2 skill key directive).
RUN . /opt/ros/${ROS_DISTRO}/setup.sh \
 && apt-get update \
 && rosdep update --rosdistro ${ROS_DISTRO} \
 && rosdep install --from-paths src -y --ignore-src \
 && colcon build --symlink-install \
 && rm -rf /var/lib/apt/lists/*

# Make Waffle Pi's upstream sensors affordable under software rendering by
# reducing only their rates. Preserve optics, samples, noise, and frame IDs.
#
# Frame RATE is the only lever that works in the optional Furnished House.
# Every camera frame there is a full ogre2 render pass over ~100 models on
# llvmpipe, and the cost is scene traversal rather than rasterization: dropping
# the image to 320x240 measured RTF 0.521 against 0.522 at 640x480 — no change
# at all. Rate does bind. With the 4 ms physics step from sim.launch.py's
# tune_physics(), measured RTF was 0.63 at 10 Hz, 0.79 at 4 Hz with a live
# subscriber, and 0.999 with the camera off entirely (8 CPUs). Simple House is
# now the lightweight default, while 4 Hz keeps every selectable world within
# the same sensor contract and retains a live camera panel in the hosted demo;
# the browser sees JPEG frames, so the low rate costs no fidelity beyond motion
# smoothness in that one panel.
#
# The lidar is the OTHER render-based sensor — gpu_lidar renders the scene
# exactly as the camera does — and halving it buys more headroom than
# slowing the camera further: uncapped RTF measured 1.15 with a 10 Hz lidar,
# 1.28 with the camera at 3 Hz instead, and 1.35 with the lidar at 5 Hz.
# 5 Hz is a principled floor rather than a shaved number: the Nav2 local
# costmap in config/nav2_params.yaml updates at 5 Hz and slam_toolbox's
# minimum_time_interval is 0.5 s, so nothing downstream consumes scans
# faster. The IMU is not render-based and costs nothing here; 200 Hz is
# simply 200 messages/second across the ros_gz bridge and the browser
# WebSocket for a panel nothing plots.
RUN python3 - <<'PYEOF'
import xml.etree.ElementTree as ET
from pathlib import Path
sdf = Path('/opt/ros/jazzy/share/turtlebot3_gazebo/models/'
           'turtlebot3_waffle_pi/model.sdf')
tree = ET.parse(sdf)
sensors = tree.getroot().findall('.//sensor')


def retune(name, kind, upstream, wanted):
    found = [s for s in sensors
             if s.get('name') == name and s.get('type') == kind]
    assert len(found) == 1, f'expected one {kind} named {name}, found {len(found)}'
    rate = found[0].find('update_rate')
    assert rate is not None and rate.text == upstream, (
        f'upstream Waffle Pi {name} rate is {rate.text if rate is not None else None},'
        f' expected {upstream}; re-verify')
    rate.text = wanted
    print(f'turtlebot3_waffle_pi {name}: {upstream}Hz -> {wanted}Hz')


retune('camera', 'camera', '30', '4')
retune('hls_lfcd_lds', 'gpu_lidar', '10', '5')
retune('tb3_imu', 'imu', '200', '50')
tree.write(sdf, encoding='unicode')
PYEOF

COPY robot-navigation/docker/entrypoint.sh /entrypoint.sh

# Bundled viewer: the demo gateway serves /opt/lichtblick on non-API GETs.
COPY --from=lichtblick /src /opt/lichtblick
COPY robot-navigation/lichtblick/layout.json /opt/lichtblick/layout.json
COPY --from=dashboard /extension/robium.dashboard-0.9.0.foxe /opt/lichtblick/robium/dashboard.foxe
COPY shared/lichtblick-dashboard/package.json /opt/lichtblick/robium/package.json
COPY shared/lichtblick-dashboard/README.md /opt/lichtblick/robium/README.md
COPY shared/lichtblick-dashboard/CHANGELOG.md /opt/lichtblick/robium/CHANGELOG.md
COPY shared/lichtblick-dashboard/deploy/preinstall-extension.mjs /opt/lichtblick/robium/preinstall-extension.mjs
RUN python3 /ws/scripts/bundle_default_extension.py /opt/lichtblick/index.html \
      --revision-file /opt/lichtblick/robium/dashboard.foxe
RUN python3 - <<'PYEOF'
from pathlib import Path
idx = Path('/opt/lichtblick/index.html')
html = idx.read_text()
token = '/*LICHTBLICK_SUITE_DEFAULT_LAYOUT_PLACEHOLDER*/'
assert token in html, 'Lichtblick default-layout placeholder missing: upstream image changed, re-verify'

# Keep the UNINJECTED page as a template. Injection is a one-shot string
# replace that consumes the placeholder, so once index.html carries a layout
# it can never carry a different one. scripts/viz_server.py fills this
# template per request instead, which is what makes lichtblick/layout.json
# editable without an image rebuild. Cheap to keep: one HTML file, not a
# second copy of the bundle.
Path('/opt/lichtblick/index.template.html').write_text(html)

layout = Path('/opt/lichtblick/layout.json').read_text()
idx.write_text(html.replace(token, layout))
print('lichtblick default layout injected (template preserved)')
PYEOF

# Keep the 3D panel's publish topics advertised.
#
# ThreeDeeRender.tsx advertises /goal_pose, /clicked_point and /initialpose in a
# useEffect whose dependency list includes the panel `context`. Every time the
# data-source context changes identity the cleanup unadvertises all three and the
# effect re-advertises — except the advertise calls are optional-chained
# (`context.advertise?.()`), so a context without `advertise` no-ops while the
# cleanup already fired. The panel settles with ZERO advertised publishers:
# foxglove_bridge shows "no longer advertising /goal_pose" as the last event,
# `ros2 topic info /goal_pose` reports "Publisher count: 0", and every clicked
# goal is dropped at the bridge before it becomes a ROS message. Nav2 is fine —
# publishing to /goal_pose from the CLI drives the robot.
#
# We consume Lichtblick as a prebuilt upstream image, so the effect's dependency
# list is not ours to fix. Neutralizing the cleanup is the narrowest change that
# restores the interaction: the advertisements simply persist for the life of the
# session. Re-advertising the same topic on a fresh channel is harmless — ROS
# allows multiple publishers on a topic, and the most recent advertise is the one
# `context.publish` routes through.
RUN python3 - <<'PYEOF'
import re
from pathlib import Path
# Match by shape, not by minified identifier names or bundle hash: both change
# whenever the upstream image is rebuilt.
pat = re.compile(
    r'\(\)=>\{(\w+)\.unadvertise\?\.\((\w+)\.goal\),'
    r'\1\.unadvertise\?\.\(\2\.point\),'
    r'\1\.unadvertise\?\.\(\2\.pose\)\}')
hits = [(p, pat.findall(p.read_text())) for p in Path('/opt/lichtblick').glob('*.js')]
hits = [(p, n) for p, n in hits if n]
assert len(hits) == 1, f'expected exactly 1 bundle with the publish-cleanup pattern, found {len(hits)}: upstream image changed, re-verify'
path, found = hits[0]
assert len(found) == 1, f'expected exactly 1 occurrence in {path.name}, found {len(found)}'
path.write_text(pat.sub('()=>{}', path.read_text()))
print(f'lichtblick publish-cleanup neutralized in {path.name}')
PYEOF
RUN chmod +x /entrypoint.sh /ws/scripts/*.sh 2>/dev/null || chmod +x /entrypoint.sh

ENV TURTLEBOT3_MODEL=waffle_pi
EXPOSE 8765
ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash"]
