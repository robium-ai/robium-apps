#!/usr/bin/env bash
# Start foxglove_bridge on the robot over SSH (detached), then verify the WS.
# The bridge sees ROS topics over localhost DDS; the browser connects to :PORT.
set -euo pipefail
ROBOT="${ROBOT:-192.0.2.10}"
PORT="${PORT:-8765}"
KEY="${KEY:-$HOME/.ssh/id_ed25519}"
SSH=(ssh -i "$KEY" -o BatchMode=yes -o ConnectTimeout=12 "ubuntu@$ROBOT")
here="$(cd "$(dirname "$0")" && pwd)"

echo "Starting foxglove_bridge on $ROBOT:$PORT ..."
"${SSH[@]}" "source /opt/ros/humble/setup.bash; source /etc/turtlebot4/setup.bash 2>/dev/null; \
  fuser -k $PORT/tcp 2>/dev/null; sleep 1; \
  setsid nohup ros2 launch foxglove_bridge foxglove_bridge_launch.xml \
    port:=$PORT address:=0.0.0.0 >/tmp/foxglove_bridge.log 2>&1 & echo started pid \$!"

echo "Waiting for WS handshake ..."
n=0
until "$here/../tests/check_ws.sh" "http://$ROBOT:$PORT" >/dev/null 2>&1; do
  n=$((n+1))
  if [ "$n" -ge 15 ]; then
    echo "BRIDGE DID NOT COME UP — last log lines:"
    "${SSH[@]}" 'tail -20 /tmp/foxglove_bridge.log' || true
    exit 1
  fi
  sleep 2
done
echo "BRIDGE UP: ws://$ROBOT:$PORT"

# Deploy + (re)launch the dock/undock helper node (turns /teleop/dock and
# /teleop/undock topic publishes into Create 3 dock/undock action goals).
echo "Deploying dock/undock helper ..."
scp -i "$KEY" -o BatchMode=yes -o ConnectTimeout=12 \
  "$here/../robot/teleop_actions.py" "ubuntu@$ROBOT:/tmp/tb4_teleop_actions.py" >/dev/null
"${SSH[@]}" "source /opt/ros/humble/setup.bash; source /etc/turtlebot4/setup.bash 2>/dev/null; \
  [ -f /tmp/tb4_teleop_actions.pid ] && kill \$(cat /tmp/tb4_teleop_actions.pid) 2>/dev/null; sleep 1; \
  nohup python3 /tmp/tb4_teleop_actions.py >/tmp/tb4_teleop_actions.log 2>&1 & echo \$! >/tmp/tb4_teleop_actions.pid; \
  echo helper pid \$(cat /tmp/tb4_teleop_actions.pid)"
echo "TELEOP HELPER UP: /teleop/dock /teleop/undock"
