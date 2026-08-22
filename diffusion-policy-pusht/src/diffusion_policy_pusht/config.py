"""Single source of truth for PushT Diffusion Policy training and evaluation."""

from __future__ import annotations

import os
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]

DATASET_REPO_ID = "lerobot/pusht"
ENV_TYPE = "pusht"
POLICY_TYPE = "diffusion"
DEVICE = os.environ.get("POLICY_DEVICE", "mps")
SEED = 1000

OFFICIAL_MODEL_ID = "lerobot/diffusion_pusht"
OFFICIAL_MODEL_REVISION = "84a7c23178445c6bbf7e1a884ff497017910f653"
OFFICIAL_MODEL_URL = "https://huggingface.co/lerobot/diffusion_pusht"
OFFICIAL_TRAINING_STEPS = 175_000
OFFICIAL_CHECKPOINT_DIR = APP_ROOT / "outputs" / "models" / "official-175k"

# Explicit values keep a LeRobot default change from silently changing this
# experiment. Execution and denoising are calibrated at the 5k gate.
N_OBS_STEPS = 2
HORIZON = 64
TRAIN_N_ACTION_STEPS = 32
NUM_TRAIN_TIMESTEPS = 100
TRAIN_NUM_INFERENCE_STEPS = 10
VISION_BACKBONE = "resnet18"

BATCH_SIZE = int(os.environ.get("DIFFUSION_BATCH_SIZE", "8"))
NUM_WORKERS = int(os.environ.get("DIFFUSION_NUM_WORKERS", "0"))

# Pipeline smoke: proves train -> checkpoint processors -> synchronous eval.
SMOKE_STEPS = 200
SMOKE_SAVE_FREQ = SMOKE_STEPS
SMOKE_LOG_FREQ = 20
SMOKE_EVAL_EPISODES = 2
SMOKE_EVAL_BATCH_SIZE = 1
SMOKE_TRAIN_OUTPUT_DIR = APP_ROOT / "outputs" / "train" / "diffusion_pusht_smoke"
SMOKE_EVAL_OUTPUT_DIR = APP_ROOT / "outputs" / "eval" / "smoke"

# One resumable learning run. The 5k checkpoint gates the longer stages.
CHECKPOINT_STEPS = (5_000, 10_000, 25_000, 50_000, 75_000, 100_000)
CALIBRATION_STEP = CHECKPOINT_STEPS[0]
TRAIN_OUTPUT_DIR = APP_ROOT / "outputs" / "train" / "diffusion_pusht"
EVAL_OUTPUT_DIR = APP_ROOT / "outputs" / "eval" / "ladder"
CALIBRATION_OUTPUT_DIR = APP_ROOT / "outputs" / "eval" / "calibration"
CALIBRATION_RESULTS = CALIBRATION_OUTPUT_DIR / "results.json"
DEMO_LADDER_MANIFEST = APP_ROOT / "outputs" / "demo" / "ladder.json"

# Calibration and benchmark seeds are disjoint and stable.
CALIBRATION_ACTION_STEPS = (8, 16, 32)
CALIBRATION_INFERENCE_STEPS = (10, 100)
CALIBRATION_SEEDS = tuple(range(11_000, 11_010))
BENCHMARK_SEEDS = tuple(range(12_000, 12_050))
# The official published evaluation used 500 layouts seeded 1000 through 1499.
# Keep this separate from the stopped local experiment's benchmark seed set.
OFFICIAL_EVAL_SEEDS = tuple(range(1_000, 1_500))
RELEASE_SUCCESS_RATE = 0.70

DEMO_PORT = int(os.environ.get("PORT", "8765"))
DEMO_DEFAULT_SHAPE = "T"
DEMO_SESSION_SECONDS = int(os.environ.get("DEMO_SESSION_SECONDS", "1800"))
DEMO_FLEET_BUDGET = int(os.environ.get("DEMO_FLEET_BUDGET", "2"))


def demo_device() -> str:
    """Prefer CUDA, then native MPS, with a CPU fallback."""
    import torch

    if torch.cuda.is_available():
        return "cuda"
    return "mps" if torch.backends.mps.is_available() else "cpu"


def _policy_args() -> list[str]:
    return [
        f"--policy.type={POLICY_TYPE}",
        f"--policy.device={DEVICE}",
        "--policy.push_to_hub=false",
        f"--policy.n_obs_steps={N_OBS_STEPS}",
        f"--policy.horizon={HORIZON}",
        f"--policy.n_action_steps={TRAIN_N_ACTION_STEPS}",
        f"--policy.num_train_timesteps={NUM_TRAIN_TIMESTEPS}",
        f"--policy.num_inference_steps={TRAIN_NUM_INFERENCE_STEPS}",
        f"--policy.vision_backbone={VISION_BACKBONE}",
    ]


def train_cmd(*, steps: int, save_freq: int, log_freq: int, output_dir: Path) -> list[str]:
    return [
        "lerobot-train",
        f"--dataset.repo_id={DATASET_REPO_ID}",
        *_policy_args(),
        f"--steps={steps}",
        f"--batch_size={BATCH_SIZE}",
        f"--num_workers={NUM_WORKERS}",
        f"--save_freq={save_freq}",
        "--save_checkpoint=true",
        "--env_eval_freq=0",
        f"--log_freq={log_freq}",
        f"--seed={SEED}",
        "--wandb.enable=false",
        f"--output_dir={output_dir}",
    ]


def train_smoke_cmd() -> list[str]:
    return train_cmd(
        steps=SMOKE_STEPS,
        save_freq=SMOKE_SAVE_FREQ,
        log_freq=SMOKE_LOG_FREQ,
        output_dir=SMOKE_TRAIN_OUTPUT_DIR,
    )


def train_initial_ladder_cmd() -> list[str]:
    return train_cmd(
        steps=CALIBRATION_STEP,
        save_freq=CALIBRATION_STEP,
        log_freq=200,
        output_dir=TRAIN_OUTPUT_DIR,
    )


def resume_ladder_cmd(target_steps: int) -> list[str]:
    checkpoint = latest_checkpoint(TRAIN_OUTPUT_DIR)
    return [
        "lerobot-train",
        f"--config_path={checkpoint / 'train_config.json'}",
        "--resume=true",
        f"--steps={target_steps}",
        f"--save_freq={target_steps}",
        "--env_eval_freq=0",
        "--wandb.enable=false",
    ]


def eval_cmd(
    policy_path: str | Path,
    n_episodes: int,
    batch_size: int,
    output_dir: Path,
    *,
    n_action_steps: int | None = None,
    num_inference_steps: int | None = None,
    seed: int = SEED,
) -> list[str]:
    cmd = [
        "lerobot-eval",
        f"--policy.path={policy_path}",
        f"--env.type={ENV_TYPE}",
        f"--eval.n_episodes={n_episodes}",
        f"--eval.batch_size={batch_size}",
        "--eval.use_async_envs=false",
        f"--seed={seed}",
        f"--policy.device={DEVICE}",
        "--policy.use_amp=false",
        f"--output_dir={output_dir}",
    ]
    if n_action_steps is not None:
        cmd.append(f"--policy.n_action_steps={n_action_steps}")
    if num_inference_steps is not None:
        cmd.append(f"--policy.num_inference_steps={num_inference_steps}")
    return cmd


def checkpoint_dir(step: int, train_dir: Path = TRAIN_OUTPUT_DIR) -> Path:
    return train_dir / "checkpoints" / f"{step:06d}" / "pretrained_model"


def latest_checkpoint(train_dir: Path = TRAIN_OUTPUT_DIR) -> Path:
    ckpt_root = train_dir / "checkpoints"
    last = ckpt_root / "last" / "pretrained_model"
    if last.is_dir():
        return last.resolve()
    candidates = sorted(ckpt_root.glob("*/pretrained_model"))
    if not candidates:
        raise FileNotFoundError(f"no checkpoint under {ckpt_root}")
    return candidates[-1]


def available_checkpoint_steps() -> tuple[int, ...]:
    return tuple(step for step in CHECKPOINT_STEPS if checkpoint_dir(step).is_dir())
