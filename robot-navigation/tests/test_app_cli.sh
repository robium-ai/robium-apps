#!/bin/sh
set -eu

APP_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TEST_DIR=$(mktemp -d "${TMPDIR:-/tmp}/robot-navigation-app.XXXXXX")
trap 'rm -rf "$TEST_DIR"' EXIT HUP INT TERM

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

mkdir -p "$TEST_DIR/bin"
cat >"$TEST_DIR/bin/docker" <<'EOF'
#!/bin/sh
printf '%s\n' "$*" >>"$DOCKER_CALLS"

case "$*" in
  "image inspect robot-navigation:latest")
    [ "${ROBIUM_TEST_IMAGE_PRESENT:-1}" = 1 ]
    ;;
esac
EOF
chmod +x "$TEST_DIR/bin/docker"

export PATH="$TEST_DIR/bin:$PATH"
export DOCKER_CALLS="$TEST_DIR/docker.calls"

help_output=$($APP_DIR/app help)
assert_contains "$help_output" "./app run"
assert_contains "$help_output" "./app doctor"
assert_not_contains "$help_output" "make run"
assert_not_contains "$help_output" "robium app"

: >"$DOCKER_CALLS"
$APP_DIR/app build >/dev/null
build_calls=$(cat "$DOCKER_CALLS")
assert_contains "$build_calls" "compose -f docker/compose.yaml build sim"

: >"$DOCKER_CALLS"
ROBIUM_TEST_IMAGE_PRESENT=1 $APP_DIR/app run >/dev/null
run_calls=$(cat "$DOCKER_CALLS")
assert_contains "$run_calls" "image inspect robot-navigation:latest"
assert_contains "$run_calls" "compose -f docker/compose.yaml --profile mapping up --abort-on-container-exit"

: >"$DOCKER_CALLS"
ROBIUM_TEST_IMAGE_PRESENT=0 $APP_DIR/app run >/dev/null
cold_run_calls=$(cat "$DOCKER_CALLS")
assert_contains "$cold_run_calls" "compose -f docker/compose.yaml build sim"
assert_contains "$cold_run_calls" "compose -f docker/compose.yaml --profile mapping up --abort-on-container-exit"

: >"$DOCKER_CALLS"
$APP_DIR/app stop >/dev/null
stop_calls=$(cat "$DOCKER_CALLS")
assert_contains "$stop_calls" "compose -f docker/compose.yaml --profile * down --remove-orphans"

echo "APP CLI PASS"
