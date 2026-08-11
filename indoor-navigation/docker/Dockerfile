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
      ros-jazzy-teleop-twist-keyboard \
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

# Make the robot's onboard camera affordable without a GPU.
#
# turtlebot3_burger_cam ships a `wideanglecamera` (fisheye, hfov 3.183 rad) with
# a 512x512 env_texture — a six-face cubemap rendered every frame at 30 Hz. On
# llvmpipe that dominates the whole simulation: measured RTF 1.15 with only the
# robot camera, 0.17 once this sensor is added. Nav2's controller and the
# smoke timeouts both assume RTF near 1.0, so the fisheye is not affordable.
#
# A pinhole camera at 10 Hz costs one render pass instead of six and looks the
# same in an Image panel. The FOV drops from 182 deg to a pi-cam-like 86 deg,
# which is the intended trade: this view exists to show what the robot sees,
# not to be a calibrated fisheye.
RUN python3 - <<'PYEOF'
import re
from pathlib import Path
sdf = Path('/opt/ros/jazzy/share/turtlebot3_gazebo/models/'
           'turtlebot3_burger_cam/model.sdf')
text = sdf.read_text()

def once(pattern, repl, s, what):
    s, n = re.subn(pattern, repl, s, flags=re.S)
    assert n == 1, f'expected exactly 1 {what}, found {n}: upstream model changed, re-verify'
    return s

text = once(r'type="wideanglecamera"', 'type="camera"', text, 'wideanglecamera sensor')
text = once(r'<update_rate>30</update_rate>', '<update_rate>10</update_rate>', text, 'camera update_rate')
text = once(r'\s*<lens>.*?</lens>', '', text, 'lens block')          # pinhole has no lens model
text = once(r'<horizontal_fov>3\.183</horizontal_fov>',
            '<horizontal_fov>1.5</horizontal_fov>', text, 'horizontal_fov')
sdf.write_text(text)
print('turtlebot3_burger_cam camera: wideangle@30Hz -> pinhole@10Hz')
PYEOF

COPY docker/entrypoint.sh /entrypoint.sh

# Bundled viewer: the demo gateway serves /opt/lichtblick on non-API GETs.
COPY --from=lichtblick /src /opt/lichtblick
COPY lichtblick/nav-layout.json /opt/lichtblick/nav-layout.json
COPY lichtblick/mapping-layout.json /opt/lichtblick/mapping-layout.json
RUN python3 - <<'PYEOF'
from pathlib import Path
idx = Path('/opt/lichtblick/index.html')
html = idx.read_text()
token = '/*LICHTBLICK_SUITE_DEFAULT_LAYOUT_PLACEHOLDER*/'
assert token in html, 'Lichtblick default-layout placeholder missing: upstream image changed, re-verify'

# Keep the UNINJECTED page as a template. Injection is a one-shot string
# replace that consumes the placeholder, so baking nav-layout into index.html
# would leave no way to serve a different layout later. The mapping dashboard
# needs a different one, and scripts/viz_server.py injects it per request from
# this template. Cheap to keep: one HTML file, not a second copy of the bundle.
Path('/opt/lichtblick/index.template.html').write_text(html)

layout = Path('/opt/lichtblick/nav-layout.json').read_text()
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

ENV TURTLEBOT3_MODEL=burger_cam
EXPOSE 8765
ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash"]
