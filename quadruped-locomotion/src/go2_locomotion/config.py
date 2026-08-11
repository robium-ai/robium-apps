"""Single source of truth for go2-locomotion run parameters.

The Makefile targets and the tests both build their Isaac Lab invocations from
these values, so a hand-run stage and the pass-bar run can never drift apart.
(Pattern lifted from apps/vla-trial and apps/manip-trial.)

WHERE THIS RUNS: everything here executes ON the RunPod GPU pod, not on the Mac.
Isaac Lab has no macOS path at all (see docs/architecture-brief.md §1). The one
thing that IS Mac-testable is the pure-Python command construction below — it
imports nothing from Isaac Lab, so tests/test_config.py can assert the command
shapes on any host without a GPU.

PROVENANCE / TRUST: task ids, script paths, and flags are sourced from the robium
`isaac-lab` skill + a ctx7 fetch (2026-07-26), NOT typed from memory. But per that
skill's standing directive — *never trust an Isaac Lab task id or script path
across releases* — RE-VERIFY at Phase 0:
  * task ids  -> `make list-envs` (list_envs.py) on the pod,
  * script paths -> against the actually-installed IsaacLab tree.
The scripts directory was reorganized into reinforcement_learning/ +
imitation_learning/ subdirs in a past release; assume it can move again.
"""

import os
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]

# --- Isaac Lab location on the pod -----------------------------------------
# Where IsaacLab was cloned + installed in Phase 0. Overridable per pod layout.
# All train/play/list scripts are resolved relative to this root, and Isaac Lab
# is normally launched with this as the CWD (so logs/ lands under it).
ISAACLAB_ROOT = Path(os.environ.get("ISAACLAB_ROOT", "/workspace/IsaacLab"))

# Script paths, relative to ISAACLAB_ROOT (RE-VERIFY against the installed tree).
TRAIN_SCRIPT = "scripts/reinforcement_learning/rsl_rl/train.py"
PLAY_SCRIPT = "scripts/reinforcement_learning/rsl_rl/play.py"
LIST_ENVS_SCRIPT = "scripts/environments/list_envs.py"

# The python interpreter that has Isaac Sim / Isaac Lab importable. Inside the
# Isaac Sim container this is the image's own python on PATH; override via env if
# the pod exposes it under a different name (e.g. isaaclab.sh's wrapped python).
PYTHON = os.environ.get("ISAACLAB_PYTHON", "python")

# --- task ------------------------------------------------------------------
# Confirmed in the supported-task list via ctx7 2026-07-26; RE-VERIFY with
# `make list-envs`. Flat first (fastest to a walking policy); rough terrain is a
# Phase-3 follow-on and its exact id must be verified, not assumed.
TASK = "Isaac-Velocity-Flat-Unitree-Go2-v0"
TASK_ROUGH = "Isaac-Velocity-Rough-Unitree-Go2-v0"  # Phase 3; verify name at runtime.

RL_LIBRARY = "rsl_rl"  # Isaac Lab default (PPO); play.py also auto-exports
#                        the policy to TorchScript + ONNX under exported/.

# Shared seed for train + play so runs reproduce.
SEED = 42

# --- run profiles ----------------------------------------------------------
# Two profiles, the vla-trial pattern:
#   SMOKE — the pass-bar run. Proves the training loop assembles and writes a
#           checkpoint (MECHANICS, not policy quality). A run this small will NOT
#           produce a walking Go2, and that is the CORRECT result — same posture
#           as vla-trial's "pipe-test proves the loop, not the score".
#   FULL  — the real ~20-40 min walking policy (thousands of parallel envs,
#           the task's own default iteration count).
#
# The numbers below are STARTING GUESSES. Pin them against MEASURED L4 throughput
# in Phase 0/2 (brief §5), then rewrite this comment with the measured basis.
SMOKE_NUM_ENVS = 32
SMOKE_MAX_ITERATIONS = 10  # override the task default down to a few iters.

FULL_NUM_ENVS = 4096  # locomotion wants thousands of parallel envs on the GPU.
# FULL deliberately does NOT override --max_iterations: it uses the task's own
# rsl_rl default training length (the skill's small-scale-first guidance — only
# the smoke run overrides it). If the full run needs a cap, add it here explicitly.

# --- video / logging -------------------------------------------------------
VIDEO_LENGTH = 200
VIDEO_INTERVAL = 2000
# Isaac Lab writes runs to <cwd>/logs/<library>/<task>/<timestamp>/. Launched
# from ISAACLAB_ROOT, that is:
LOG_ROOT = ISAACLAB_ROOT / "logs" / RL_LIBRARY


# --- command builders ------------------------------------------------------
# Pure string construction — no Isaac Lab import — so these are unit-testable on
# the Mac (tests/test_config.py) even though they only RUN on the pod.

def train_cmd(full: bool = False, video: bool = False) -> list[str]:
    """Build the rsl_rl train.py invocation.

    full=False -> SMOKE profile (the pass-bar run: tiny, mechanics-only).
    full=True  -> FULL profile (the real walking-policy run).
    """
    num_envs = FULL_NUM_ENVS if full else SMOKE_NUM_ENVS
    cmd = [
        PYTHON, TRAIN_SCRIPT,
        "--task", TASK,
        "--headless",
        "--num_envs", str(num_envs),
        "--seed", str(SEED),
    ]
    if not full:
        # Smoke overrides the task's default iteration count down to a few.
        cmd += ["--max_iterations", str(SMOKE_MAX_ITERATIONS)]
    if video:
        # Off-screen video capture also needs --enable_cameras.
        cmd += [
            "--video",
            "--video_length", str(VIDEO_LENGTH),
            "--video_interval", str(VIDEO_INTERVAL),
            "--enable_cameras",
        ]
    return cmd


def play_cmd(num_envs: int = 32, video: bool = False) -> list[str]:
    """Build the rsl_rl play.py invocation (loads latest checkpoint, rolls out)."""
    cmd = [PYTHON, PLAY_SCRIPT, "--task", TASK, "--num_envs", str(num_envs)]
    if video:
        cmd += ["--video", "--video_length", str(VIDEO_LENGTH), "--enable_cameras"]
    return cmd


def list_envs_cmd() -> list[str]:
    """List the currently-registered Isaac Lab tasks (source of truth for TASK)."""
    return [PYTHON, LIST_ENVS_SCRIPT]
