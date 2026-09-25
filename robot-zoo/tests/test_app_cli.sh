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
check "doctor is advertised"       "./app help | grep -q './app doctor'"
check "doctor passes"              "./app doctor | grep -q 'DOCTOR PASS'"
check "unknown command exits 1"     "! ./app nonsense"
check "robium-app.yaml present"     "[ -f robium-app.yaml ]"
check "architecture brief present"  "[ -f docs/architecture-brief.md ]"
check "native viewer app present"   "[ -f src/robot_zoo/app.py ]"
check "Gradio UI present"           "[ -f src/robot_zoo/gradio_ui.py ]"
check "simulation manager present"  "[ -f src/robot_zoo/simulation.py ]"
check "Pygame is not a dependency"  "! grep -q pygame pyproject.toml"
check "Gradio is locked"            "grep -q 'name = \"gradio\"' uv.lock"
check "viewer uses native panels"   "grep -q 'show_left_ui=True' src/robot_zoo/simulation.py && grep -q 'show_right_ui=True' src/robot_zoo/simulation.py"
check "Linux uses native Qt/X11"     "grep -q 'gui=\"qt\"' src/robot_zoo/native_app.py && grep -q 'python-xlib' pyproject.toml"
check "controller owns shutdown"     "grep -q 'window.events.closed' src/robot_zoo/native_app.py"

[ $fail -eq 0 ] && echo "APP CLI PASS" || { echo "APP CLI FAIL"; exit 1; }
