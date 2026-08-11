#!/usr/bin/env bash
# Hardware-in-the-loop smoke for tb4-teleop.
# Requires: robot powered + on RobotWiFi + foxglove_bridge running (make bridge).
# Topic checks run ON the robot over SSH, so the Mac needs no ROS install.
# All motion commands are ZERO velocity — the robot does not move.
set -uo pipefail
ROBOT="${ROBOT:-192.0.2.10}"
PORT="${PORT:-8765}"
KEY="${KEY:-$HOME/.ssh/id_ed25519}"
here="$(cd "$(dirname "$0")" && pwd)"
SSH=(ssh -i "$KEY" -o BatchMode=yes -o ConnectTimeout=12 "ubuntu@$ROBOT")
SRC='source /opt/ros/humble/setup.bash; source /etc/turtlebot4/setup.bash 2>/dev/null'

echo "== 1/4 robot reachable =="
ping -c2 -t3 "$ROBOT" >/dev/null 2>&1 || { echo "FAIL: robot $ROBOT unreachable"; exit 1; }
echo OK

echo "== 2/4 bridge WS up =="
"$here/check_ws.sh" "http://$ROBOT:$PORT" >/dev/null 2>&1 || { echo "FAIL: bridge WS down (run: make bridge)"; exit 1; }
echo OK

echo "== 3/4 /scan flowing =="
"${SSH[@]}" "$SRC; timeout 8 ros2 topic hz /scan 2>/dev/null | head -3" | grep -q "average rate" \
  || { echo "FAIL: /scan not publishing"; exit 1; }
echo OK

echo "== 4/4 /cmd_vel accepts a zero Twist (no motion) =="
# -w 0: do NOT wait for a matching subscription. The Create 3 base subscribes in a
# separate FastDDS realm invisible to the Pi's CycloneDDS, so --once (default -w 1)
# hangs forever waiting for a subscriber that never appears from this side.
"${SSH[@]}" "$SRC; timeout 6 ros2 topic pub --once -w 0 /cmd_vel geometry_msgs/msg/Twist \
  '{linear: {x: 0.0, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}' 2>&1" \
  | grep -q "publishing" || { echo "FAIL: /cmd_vel publish rejected"; exit 1; }
echo OK

echo "TB4-TELEOP SMOKE PASS"
