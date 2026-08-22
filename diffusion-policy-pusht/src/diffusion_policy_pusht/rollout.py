"""Deterministic single-environment Diffusion Policy rollouts for PushT."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import gymnasium as gym
import numpy as np
import torch
from lerobot.configs.policies import PreTrainedConfig
from lerobot.envs.utils import preprocess_observation
from lerobot.policies.diffusion.modeling_diffusion import DiffusionPolicy
from lerobot.policies.factory import make_pre_post_processors

from diffusion_policy_pusht import config, shapes

MAX_EPISODE_STEPS = 300


@dataclass(frozen=True)
class RolloutStep:
    step: int
    total: int
    frame: np.ndarray
    action: np.ndarray | None
    reward: float
    coverage: float
    max_reward: float
    max_coverage: float
    done: bool = False
    success: bool = False
    aborted: bool = False


@dataclass(frozen=True)
class RolloutResult:
    seed: int
    shape: str
    success: bool
    aborted: bool
    steps: int
    max_reward: float
    max_coverage: float
    sum_reward: float
    elapsed_s: float

    def to_dict(self) -> dict:
        return {
            "seed": self.seed,
            "shape": self.shape,
            "success": self.success,
            "aborted": self.aborted,
            "steps": self.steps,
            "max_reward": self.max_reward,
            "max_coverage": self.max_coverage,
            "sum_reward": self.sum_reward,
            "elapsed_s": self.elapsed_s,
        }


def make_env(shape: str = "T"):
    if shape not in shapes.SHAPES:
        raise ValueError(f"unknown shape {shape!r}; choose from {list(shapes.SHAPES)}")
    if shape == "T":
        # Benchmark parity requires the upstream implementation unchanged. Its
        # historical compound-body inertia differs from our generalized letter
        # builder even though the visible T geometry is identical.
        return gym.make(
            "gym_pusht/PushT-v0",
            obs_type="pixels_agent_pos",
            render_mode="rgb_array",
        )
    return gym.make(
        shapes.ENV_ID,
        shape=shape,
        obs_type="pixels_agent_pos",
        render_mode="rgb_array",
    )


class DiffusionCheckpoint:
    """One loaded checkpoint with adjustable inference-only settings."""

    def __init__(self, path: str | Path, device: str | None = None):
        self.path = Path(path).resolve()
        if not self.path.is_dir():
            raise FileNotFoundError(f"checkpoint directory does not exist: {self.path}")
        required = (
            "config.json",
            "model.safetensors",
            "policy_preprocessor.json",
            "policy_postprocessor.json",
        )
        missing = [name for name in required if not (self.path / name).is_file()]
        if missing:
            raise FileNotFoundError(f"checkpoint {self.path} is missing: {', '.join(missing)}")

        policy_cfg = PreTrainedConfig.from_pretrained(self.path)
        if policy_cfg.type != "diffusion":
            raise ValueError(f"checkpoint {self.path} is {policy_cfg.type!r}, expected 'diffusion'")
        policy_cfg.device = device or config.demo_device()
        self.device = policy_cfg.device
        self.policy = DiffusionPolicy.from_pretrained(self.path, config=policy_cfg)
        self.policy.eval()
        self.preprocessor, self.postprocessor = make_pre_post_processors(
            policy_cfg=policy_cfg,
            pretrained_path=str(self.path),
            preprocessor_overrides={"device_processor": {"device": self.device}},
        )

    @property
    def n_action_steps(self) -> int:
        return int(self.policy.config.n_action_steps)

    @property
    def num_inference_steps(self) -> int:
        return int(self.policy.diffusion.num_inference_steps)

    def configure(self, *, n_action_steps: int, num_inference_steps: int) -> None:
        max_actions = self.policy.config.horizon - self.policy.config.n_obs_steps + 1
        if not 1 <= n_action_steps <= max_actions:
            raise ValueError(f"n_action_steps must be in [1, {max_actions}], got {n_action_steps}")
        if not 1 <= num_inference_steps <= self.policy.config.num_train_timesteps:
            raise ValueError(
                "num_inference_steps must not exceed training diffusion steps "
                f"({self.policy.config.num_train_timesteps}), got {num_inference_steps}"
            )
        self.policy.config.n_action_steps = n_action_steps
        self.policy.diffusion.num_inference_steps = num_inference_steps
        self.policy.reset()

    def run(
        self,
        *,
        seed: int,
        shape: str = "T",
        on_step: Callable[[RolloutStep], None] | None = None,
        should_abort: Callable[[], bool] | None = None,
    ) -> RolloutResult:
        torch.manual_seed(seed)
        self.policy.reset()
        env = make_env(shape)
        started = time.perf_counter()
        max_reward = 0.0
        max_coverage = 0.0
        sum_reward = 0.0
        success = False
        aborted = False
        steps = 0
        try:
            obs, _ = env.reset(seed=seed)
            if on_step:
                on_step(
                    RolloutStep(
                        step=0,
                        total=MAX_EPISODE_STEPS,
                        frame=obs["pixels"].copy(),
                        action=None,
                        reward=0.0,
                        coverage=0.0,
                        max_reward=0.0,
                        max_coverage=0.0,
                    )
                )
            for step in range(MAX_EPISODE_STEPS):
                if should_abort and should_abort():
                    aborted = True
                    break
                batch = self.preprocessor(preprocess_observation(obs))
                with torch.inference_mode():
                    action = self.policy.select_action(batch)
                action = self.postprocessor(action)
                action_np = action.squeeze(0).cpu().numpy().astype(np.float32)

                obs, reward, terminated, truncated, info = env.step(action_np)
                steps = step + 1
                reward_f = float(reward)
                coverage_f = float(info.get("coverage", 0.0))
                sum_reward += reward_f
                max_reward = max(max_reward, reward_f)
                max_coverage = max(max_coverage, coverage_f)
                success = success or bool(info.get("is_success", False))
                event = RolloutStep(
                    step=steps,
                    total=MAX_EPISODE_STEPS,
                    frame=obs["pixels"].copy(),
                    action=action_np,
                    reward=reward_f,
                    coverage=coverage_f,
                    max_reward=max_reward,
                    max_coverage=max_coverage,
                    success=success,
                )
                if on_step:
                    on_step(event)
                if terminated or truncated:
                    break

            if on_step:
                on_step(
                    RolloutStep(
                        step=steps,
                        total=MAX_EPISODE_STEPS,
                        frame=obs["pixels"].copy(),
                        action=None,
                        reward=0.0,
                        coverage=max_coverage,
                        max_reward=max_reward,
                        max_coverage=max_coverage,
                        done=True,
                        success=success,
                        aborted=aborted,
                    )
                )
        finally:
            env.close()
        return RolloutResult(
            seed=seed,
            shape=shape,
            success=success,
            aborted=aborted,
            steps=steps,
            max_reward=max_reward,
            max_coverage=max_coverage,
            sum_reward=sum_reward,
            elapsed_s=time.perf_counter() - started,
        )
