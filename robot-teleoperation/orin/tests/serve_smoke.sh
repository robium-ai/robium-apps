#!/usr/bin/env bash
# Console-contract smoke: build+run the console container, assert it serves the page with
# env applied. Webcam + live drive are manual HIL (Task 8).
set -uo pipefail
cd "$(dirname "$0")/.."
CMP="docker compose -f docker/compose.yaml"
ROBOT_HOST=10.0.0.9 $CMP up -d --build console || { echo "BUILD/UP FAILED"; exit 1; }
trap '$CMP down >/dev/null 2>&1' EXIT
n=0; until curl -sf http://localhost:8080/ >/dev/null 2>&1; do
  n=$((n+1)); [ "$n" -ge 20 ] && { echo "PAGE NOT SERVED"; exit 1; }; sleep 1; done
curl -sf http://localhost:8080/ | grep -q 'tb4-teleop console' || { echo "HTML MARKER MISSING"; exit 1; }
curl -sf http://localhost:8080/env.js | grep -q '10.0.0.9' || { echo "ENV NOT SUBSTITUTED"; exit 1; }
echo "ORIN CONSOLE SERVE OK"
