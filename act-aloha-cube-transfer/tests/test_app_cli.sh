#!/bin/sh
set -eu

APP_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TEST_DIR=$(mktemp -d "${TMPDIR:-/tmp}/act-aloha-cube-transfer-app.XXXXXX")
RUN_WRAPPER_PID=""
trap 'if [ -n "$RUN_WRAPPER_PID" ]; then kill "$RUN_WRAPPER_PID" 2>/dev/null || true; fi; rm -rf "$TEST_DIR"' EXIT HUP INT TERM

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

assert_contains() {
  haystack=$1
  needle=$2
  case "$haystack" in
    *"$needle"*) ;;
    *) fail "expected output to contain: $needle" ;;
  esac
}

assert_not_contains() {
  haystack=$1
  needle=$2
  case "$haystack" in
    *"$needle"*) fail "expected output not to contain: $needle" ;;
    *) ;;
  esac
}

mkdir -p "$TEST_DIR/bin" "$TEST_DIR/state"

cat >"$TEST_DIR/bin/uv" <<'EOF'
#!/bin/sh
printf '%s\n' "$*" >>"$UV_CALLS"
case "$*" in
  "run python -m act_aloha_cube_transfer.demo.app")
    echo "DEMO READY"
    while :; do sleep 1; done
    ;;
esac
EOF
chmod +x "$TEST_DIR/bin/uv"

export PATH="$TEST_DIR/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export UV_CALLS="$TEST_DIR/uv.calls"
export ROBIUM_APP_STATE_DIR="$TEST_DIR/state"
export ACT_ALOHA_MODEL_DIR="$TEST_DIR/model"
export PORT=48766

help_output=$($APP_DIR/app help)
for command in doctor build run status logs stop; do
  assert_contains "$help_output" "./app $command"
done
assert_not_contains "$help_output" "./app smoke"
assert_not_contains "$help_output" "make demo"

doctor_output=$($APP_DIR/app doctor)
assert_contains "$doctor_output" "DOCTOR PASS"
assert_contains "$doctor_output" "checkpoint not prepared"

: >"$UV_CALLS"
$APP_DIR/app build >/dev/null
build_calls=$(cat "$UV_CALLS")
assert_contains "$build_calls" "sync"
assert_contains "$build_calls" "run python -m act_aloha_cube_transfer.run prepare-official"

mkdir -p "$ACT_ALOHA_MODEL_DIR"
printf '%s\n' '{"status":"ready"}' >"$ACT_ALOHA_MODEL_DIR/manifest.json"

: >"$UV_CALLS"
$APP_DIR/app run >/dev/null 2>&1 &
RUN_WRAPPER_PID=$!

n=0
until [ -s "$TEST_DIR/state/app.pid" ]; do
  n=$((n + 1))
  [ "$n" -lt 50 ] || fail "run did not create a pid file"
  sleep 0.1
done

status_output=$($APP_DIR/app status)
assert_contains "$status_output" "ACT ALOHA Cube Transfer: RUNNING"
assert_contains "$status_output" "http://localhost:48766"

$APP_DIR/app logs >"$TEST_DIR/logs.out" 2>&1 &
logs_pid=$!
sleep 0.2
kill "$logs_pid" 2>/dev/null || true
wait "$logs_pid" 2>/dev/null || true
assert_contains "$(cat "$TEST_DIR/logs.out")" "DEMO READY"

$APP_DIR/app stop >/dev/null
wait "$RUN_WRAPPER_PID"
RUN_WRAPPER_PID=""

stopped_output=$($APP_DIR/app status)
assert_contains "$stopped_output" "ACT ALOHA Cube Transfer: STOPPED"

run_calls=$(cat "$UV_CALLS")
assert_contains "$run_calls" "run python -m act_aloha_cube_transfer.demo.app"

echo "APP CLI PASS"
