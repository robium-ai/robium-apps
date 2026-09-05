#!/usr/bin/env bash
# The ./app surface must behave before anything behind it is trusted.
set -euo pipefail
cd "$(dirname "$0")/.."

fail=0
check() {
  if eval "$2" >/dev/null 2>&1; then echo "ok: $1"; else echo "FAIL: $1"; fail=1; fi
}

check "app is executable"           "[ -x ./app ]"
check "help works"                  "./app help"
check "unknown command exits 1"     "! ./app nonsense"
check "robium-app.yaml present"     "[ -f robium-app.yaml ]"
check "architecture brief present"  "[ -f docs/architecture-brief.md ]"
check "scene ships with the package" "[ -f src/smolvla_mbot_push/sim/scene.xml ]"

[ $fail -eq 0 ] && echo "APP CLI PASS" || { echo "APP CLI FAIL"; exit 1; }
