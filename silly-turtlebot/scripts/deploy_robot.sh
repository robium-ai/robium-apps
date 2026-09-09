#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: $0 ubuntu@ROBOT_IP" >&2
  exit 2
fi

target="$1"
app_root="$(cd "$(dirname "$0")/.." && pwd)"
remote_root="silly-turtlebot"

ssh -o BatchMode=yes -o ConnectTimeout=12 "$target" \
  "mkdir -p '${remote_root}'"
rsync -az \
  --exclude build --exclude install --exclude log \
  "${app_root}/robot/" "${target}:${remote_root}/robot/"
ssh -o BatchMode=yes -o ConnectTimeout=12 "$target" \
  "cd '${remote_root}/robot' && chmod +x build.sh run_bridge.sh smoke.sh && ./build.sh && \
   { command -v espeak-ng >/dev/null || sudo -n apt-get install -y espeak-ng; } && \
   sudo -n install -d /etc/systemd/system/turtlebot4.service.d && \
   sudo -n install -m 0644 systemd/turtlebot4-restart.conf /etc/systemd/system/turtlebot4.service.d/restart.conf && \
   sudo -n install -m 0644 systemd/silly-turtlebot.service /etc/systemd/system/silly-turtlebot.service && \
   sudo -n systemctl daemon-reload && \
   sudo -n systemctl enable --now silly-turtlebot.service"

echo "robot overlay deployed; TurtleBot retry + Silly Nav2 services enabled at ${target}:${remote_root}"
