#!/usr/bin/env bash
set -euo pipefail

if [[ "${DEMO_STARTUP_MODE:-live}" == "idle" ]]; then
  echo "GO2_IDLE_READY"
  exec sleep infinity
fi

: "${DEMO_CAPABILITY:?DEMO_CAPABILITY is required}"

data_root="${GO2_DATA_ROOT:-/models/quadruped}"
archive="${GO2_ARCHIVE:-${data_root}/go2_artifacts.tar.gz}"
run_root="${data_root}/run"
expected_sha="${GO2_ARCHIVE_SHA256:-}"
marker="${run_root}/.archive-sha256"

if [[ ! -f "${archive}" ]]; then
  echo "GO2_STARTUP_FAILED archive_missing:${archive}" >&2
  exit 2
fi

actual_sha="$(sha256sum "${archive}" | awk '{print $1}')"
if [[ -n "${expected_sha}" && "${actual_sha}" != "${expected_sha}" ]]; then
  echo "GO2_STARTUP_FAILED archive_sha256_mismatch" >&2
  exit 3
fi

if [[ ! -f "${marker}" ]] || [[ "$(<"${marker}")" != "${actual_sha}" ]]; then
  staging="${data_root}/run.staging"
  rm -rf "${staging}"
  mkdir -p "${staging}"
  # RunPod network volumes use root-squash; preserve bytes, not the archive's
  # historical workstation UID/GID.
  tar --no-same-owner -xzf "${archive}" -C "${staging}"
  printf '%s\n' "${actual_sha}" > "${staging}/.archive-sha256"
  rm -rf "${run_root}"
  mv "${staging}" "${run_root}"
fi

isaaclab_root="${ISAACLAB_ROOT:-/workspace/isaaclab}"
play_script="${isaaclab_root}/scripts/reinforcement_learning/rsl_rl/play.py"
live_script="${data_root}/live_demo.py"
"${isaaclab_root}/isaaclab.sh" -p \
  /opt/robium/quadruped-locomotion/scripts/live_demo_patch.py \
  --play "${play_script}" --output "${live_script}"

iteration="${GO2_CHECKPOINT_ITERATION:-1999}"
checkpoint="${GO2_CHECKPOINT:-$(find "${run_root}/logs/rsl_rl" -name "model_${iteration}.pt" -type f -print -quit)}"
if [[ -z "${checkpoint}" || ! -f "${checkpoint}" ]]; then
  echo "GO2_STARTUP_FAILED checkpoint_missing:model_${iteration}.pt" >&2
  exit 4
fi

export PYTHONPATH="${isaaclab_root}/scripts/reinforcement_learning/rsl_rl${PYTHONPATH:+:${PYTHONPATH}}"
echo "GO2_LAUNCH task=${GO2_TASK:-Isaac-Velocity-Flat-Unitree-Go2-v0} checkpoint=model_${iteration}.pt"
exec "${isaaclab_root}/isaaclab.sh" -p "${live_script}" \
  --task "${GO2_TASK:-Isaac-Velocity-Flat-Unitree-Go2-v0}" \
  --num_envs 1 \
  --checkpoint "${checkpoint}" \
  --enable_cameras \
  --device cuda \
  --headless
