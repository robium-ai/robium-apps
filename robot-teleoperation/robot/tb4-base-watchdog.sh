#!/bin/bash
# tb4-base-watchdog — auto-recover the Create 3 base when its ROS 2 app wedges.
#
# The Create 3's onboard ROS 2 application periodically wedges (known iRobot
# firmware issue), typically after a Pi reboot or Wi-Fi/network change: the base
# still boots (chime + web server) but /motion_control drops off the graph and
# STOPS subscribing to /cmd_vel, so the robot won't drive. The documented fix is
# "Restart application", which is just POST /api/restart-app on the base web UI.
#
# This loop watches /cmd_vel's subscription count (>=1 == base is listening) and,
# when it stays 0 for two consecutive checks, POSTs the restart. Recovery ~30 s,
# invisible to the operator. Logs to stdout (journald: journalctl -u tb4-base-watchdog).
set -o pipefail
source /etc/turtlebot4/setup.bash 2>/dev/null

BASE_URL="${BASE_URL:-http://192.168.186.2}"
CHECK_INTERVAL="${CHECK_INTERVAL:-30}"   # seconds between health checks
COOLDOWN="${COOLDOWN:-60}"               # seconds to wait after triggering a restart
FAIL_THRESHOLD="${FAIL_THRESHOLD:-2}"    # consecutive bad checks before acting

log() { echo "$(date -Is) tb4-base-watchdog: $*"; }

log "started (base=$BASE_URL interval=${CHECK_INTERVAL}s cooldown=${COOLDOWN}s)"
fails=0
while true; do
  # /cmd_vel subscription count: the base (motion_control) is the only subscriber,
  # so >=1 means the base app is alive and will act on drive commands.
  subs=$(timeout 8 ros2 topic info /cmd_vel 2>/dev/null | awk -F': ' '/Subscription count/{print $2}')
  subs=${subs:-0}
  if [ "$subs" -ge 1 ] 2>/dev/null; then
    fails=0
  else
    fails=$((fails + 1))
    mc=$(timeout 8 ros2 node list 2>/dev/null | grep -c motion_control)
    log "unhealthy check #$fails (/cmd_vel subs=$subs, motion_control nodes=$mc)"
    if [ "$fails" -ge "$FAIL_THRESHOLD" ]; then
      code=$(curl -s -o /dev/null -w '%{http_code}' -X POST \
        -H 'Content-Type: application/json' -d '{}' --max-time 15 \
        "$BASE_URL/api/restart-app")
      log "base app WEDGED -> POST /api/restart-app returned HTTP $code; cooldown ${COOLDOWN}s"
      fails=0
      sleep "$COOLDOWN"
      continue
    fi
  fi
  sleep "$CHECK_INTERVAL"
done
