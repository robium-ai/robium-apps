#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

fail=0
check() {
  if eval "$2" >/dev/null 2>&1; then echo "ok: $1"; else echo "FAIL: $1"; fail=1; fi
}

check "app is executable"              "[ -x ./app ]"
check "help works"                     "./app help"
check "run is advertised"              "./app help | grep -q './app run'"
check "check is advertised"            "./app help | grep -q './app check'"
check "unknown command exits nonzero"   "! ./app nonsense"
check "manifest is present"             "[ -f robium-app.yaml ]"
check "architecture brief is present"   "[ -f docs/architecture-brief.md ]"
check "thumbnail is present"            "[ -f assets/stills/car-racing-ppo-macos.png ]"
check "check is a manifest verb"        "grep -A3 '^  check:' robium-app.yaml | grep -q './app check'"
check "checkpoint revision is pinned"   "grep -q 'a3d30ae5f460c866df89364e14ceee7e9f5949ce' src/car_racing_ppo/runtime.py"
check "checkpoint checksum is pinned"   "grep -q 'edb9a2d98c51172c3723d2b1cc2a752a4c3832f14a3d2b1200297f4d4ea763ca' src/car_racing_ppo/runtime.py"

[ "$fail" -eq 0 ] && echo "APP CLI PASS" || { echo "APP CLI FAIL"; exit 1; }
