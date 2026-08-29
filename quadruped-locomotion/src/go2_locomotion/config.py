"""Runtime configuration and Isaac Lab command construction.

The application runs on a Linux NVIDIA GPU host. The wrapper remains pure
Python so its command and evidence paths can be checked on any development
machine before paid compute is involved.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]
ISAACLAB_ROOT = Path(os.environ.get("ISAACLAB_ROOT", "/workspace/IsaacLab"))
ISAACLAB_LAUNCHER = os.environ.get(
    "ISAACLAB_LAUNCHER", str(ISAACLAB_ROOT / "isaaclab.sh")
)
CLI_STYLE = os.environ.get("ISAACLAB_CLI_STYLE", "unified")

TASK = os.environ.get("GO2_TASK", "Isaac-Velocity-Flat-Unitree-Go2-v0")
RL_LIBRARY = "rsl_rl"
SEED = int(os.environ.get("GO2_SEED", "42"))

LIST_ENVS_SCRIPT = "scripts/environments/list_envs.py"
LEGACY_TRAIN_SCRIPT = "scripts/reinforcement_learning/rsl_rl/train.py"
LEGACY_PLAY_SCRIPT = "scripts/reinforcement_learning/rsl_rl/play.py"

LOG_ROOT = ISAACLAB_ROOT / "logs" / RL_LIBRARY
VIDEO_LENGTH = int(os.environ.get("GO2_VIDEO_LENGTH", "200"))
VIDEO_INTERVAL = int(os.environ.get("GO2_VIDEO_INTERVAL", "100"))


@dataclass(frozen=True)
class RunProfile:
    name: str
    num_envs: int | None
    max_iterations: int | None


SMOKE = RunProfile(
    "smoke",
    int(os.environ.get("GO2_SMOKE_NUM_ENVS", "32")),
    int(os.environ.get("GO2_SMOKE_MAX_ITERATIONS", "10")),
)
FULL = RunProfile(
    "full",
    int(value) if (value := os.environ.get("GO2_FULL_NUM_ENVS")) else None,
    int(value) if (value := os.environ.get("GO2_FULL_MAX_ITERATIONS")) else None,
)
PROFILES = {profile.name: profile for profile in (SMOKE, FULL)}


def _launcher() -> list[str]:
    return [ISAACLAB_LAUNCHER]


def _workflow(kind: str) -> list[str]:
    """Return a current unified workflow, with an explicit legacy escape hatch."""
    if CLI_STYLE == "unified":
        return _launcher() + [kind, "--rl_library", RL_LIBRARY]
    if CLI_STYLE == "legacy":
        script = LEGACY_TRAIN_SCRIPT if kind == "train" else LEGACY_PLAY_SCRIPT
        return _launcher() + ["-p", script]
    raise ValueError("ISAACLAB_CLI_STYLE must be 'unified' or 'legacy'")


def train_cmd(profile: str = "smoke", video: bool = False) -> list[str]:
    selected = PROFILES[profile]
    cmd = _workflow("train") + [
        "--task",
        TASK,
        "--seed",
        str(SEED),
    ]
    if selected.num_envs is not None:
        cmd += ["--num_envs", str(selected.num_envs)]
    cmd += ["--viz", "none"] if CLI_STYLE == "unified" else ["--headless"]
    if selected.max_iterations is not None:
        cmd += ["--max_iterations", str(selected.max_iterations)]
    if video:
        cmd += [
            "--video",
            "--video_length",
            str(VIDEO_LENGTH),
            "--video_interval",
            str(VIDEO_INTERVAL),
            "--enable_cameras",
        ]
    return cmd


def play_cmd(
    checkpoint: str = "latest", num_envs: int = 1, video: bool = False
) -> list[str]:
    cmd = _workflow("play") + [
        "--task",
        TASK,
        "--num_envs",
        str(num_envs),
        "--checkpoint",
        checkpoint,
    ]
    if CLI_STYLE == "unified" and video:
        cmd += ["--viz", "none"]
    elif CLI_STYLE == "legacy" and video:
        cmd += ["--headless"]
    if video:
        cmd += ["--video", "--video_length", str(VIDEO_LENGTH), "--enable_cameras"]
    return cmd


def list_envs_cmd() -> list[str]:
    return _launcher() + ["-p", LIST_ENVS_SCRIPT]


def checkpoints() -> set[Path]:
    if not LOG_ROOT.exists():
        return set()
    return {path.resolve() for path in LOG_ROOT.rglob("model_*.pt") if path.is_file()}
