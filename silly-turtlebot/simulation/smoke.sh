#!/usr/bin/env bash
set -euo pipefail

bridge_url="${SILLY_ROBOT_URL:-http://127.0.0.1:8088}"
console_url="${SILLY_CONSOLE_URL:-http://127.0.0.1:8091}"
deadline=$((SECONDS + ${SILLY_SIM_STARTUP_TIMEOUT:-240}))

echo "Waiting for Gazebo, Nav2, and the simulated OAK-D at ${bridge_url} ..."
while (( SECONDS < deadline )); do
  health="$(curl --silent --show-error --max-time 3 "${bridge_url}/v1/health" 2>/dev/null || true)"
  if HEALTH_JSON="$health" python3 - <<'PY'
import json
import os

try:
    health = json.loads(os.environ["HEALTH_JSON"])
except (KeyError, json.JSONDecodeError):
    raise SystemExit(1)

ready = (
    health.get("status") == "ok"
    and health.get("navigate_to_pose") is True
    and health.get("drive_on_heading") is True
    and health.get("spin") is True
    and health.get("cameras", {}).get("primary", {}).get("fresh") is True
    and {"dock", "kitchen", "living_room"}.issubset(health.get("locations", []))
)
raise SystemExit(0 if ready else 1)
PY
  then
    printf '%s\n' "$health"
    curl --fail --silent --show-error --max-time 10 \
      "${bridge_url}/v1/camera/primary" -o /tmp/silly-turtlebot-sim.jpg
    test -s /tmp/silly-turtlebot-sim.jpg
    mission_health="$(curl --fail --silent --show-error --max-time 10 \
      "${console_url}/api/health")"
    MISSION_HEALTH_JSON="$mission_health" python3 - <<'PY'
import json
import os

health = json.loads(os.environ["MISSION_HEALTH_JSON"])
raise SystemExit(0 if health.get("status") == "ok" else 1)
PY
    echo "SILLY TURTLEBOT GAZEBO SMOKE PASS"
    exit 0
  fi
  sleep 3
done

echo "Simulator did not become ready before the timeout." >&2
printf '%s\n' "${health:-no bridge response}" >&2
exit 1
