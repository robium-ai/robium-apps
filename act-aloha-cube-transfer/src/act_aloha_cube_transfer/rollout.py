"""Seeded, chunk-aware ACT rollouts for ALOHA Transfer Cube."""

from __future__ import annotations

import time
from collections.abc import Callable

import numpy as np
import torch

from act_aloha_cube_transfer import config
from act_aloha_cube_transfer.environment import make_env, validate_observation
from act_aloha_cube_transfer.types import RolloutResult, RolloutStep

PHASES = {
    0: "reaching",
    1: "right gripper contact",
    2: "cube lifted",
    3: "left gripper contact",
    4: "transfer complete",
}


def phase_for_reward(reward: float) -> str:
    return PHASES.get(int(reward), f"simulator reward {reward:g}")


def run_rollout(
    checkpoint,
    *,
    seed: int,
    execution_horizon: int,
    on_step: Callable[[RolloutStep], None] | None = None,
    should_abort: Callable[[], bool] | None = None,
    env_factory: Callable[[], object] = make_env,
) -> RolloutResult:
    if execution_horizon not in config.EXECUTION_HORIZONS:
        raise ValueError(f"execution_horizon must be one of {config.EXECUTION_HORIZONS}")

    torch.manual_seed(seed)
    np.random.seed(seed)
    checkpoint.reset()
    env = env_factory()
    started = time.perf_counter()
    inference_seconds: list[float] = []
    policy_calls = 0
    steps = 0
    max_reward = 0.0
    sum_reward = 0.0
    success = False
    aborted = False
    ended = False
    observation = None
    try:
        observation, _ = env.reset(seed=seed)
        validate_observation(observation)
        if on_step:
            on_step(
                RolloutStep(
                    step=0,
                    total=config.MAX_EPISODE_STEPS,
                    frame=observation["pixels"]["top"].copy(),
                    state=observation["agent_pos"].astype(np.float32).copy(),
                    action=None,
                    reward=0.0,
                    phase=phase_for_reward(0),
                    policy_call=0,
                    chunk_index=0,
                    inference_s=0.0,
                )
            )

        while steps < config.MAX_EPISODE_STEPS and not success:
            if should_abort and should_abort():
                aborted = True
                break
            inference_started = time.perf_counter()
            actions = checkpoint.predict_chunk(observation)
            inference_s = time.perf_counter() - inference_started
            inference_seconds.append(inference_s)
            policy_calls += 1

            for chunk_index, action in enumerate(actions[:execution_horizon]):
                if should_abort and should_abort():
                    aborted = True
                    break
                observation, reward, terminated, truncated, info = env.step(action)
                validate_observation(observation)
                steps += 1
                reward_f = float(reward)
                max_reward = max(max_reward, reward_f)
                sum_reward += reward_f
                success = success or bool(info.get("is_success", False)) or reward_f >= 4.0
                ended = bool(terminated or truncated)
                if on_step:
                    on_step(
                        RolloutStep(
                            step=steps,
                            total=config.MAX_EPISODE_STEPS,
                            frame=observation["pixels"]["top"].copy(),
                            state=observation["agent_pos"].astype(np.float32).copy(),
                            action=np.asarray(action, dtype=np.float32).copy(),
                            reward=reward_f,
                            phase=phase_for_reward(reward_f),
                            policy_call=policy_calls,
                            chunk_index=chunk_index,
                            inference_s=inference_s,
                            success=success,
                        )
                    )
                if success or ended or steps >= config.MAX_EPISODE_STEPS:
                    break
            if aborted or ended:
                break

        if on_step and observation is not None:
            on_step(
                RolloutStep(
                    step=steps,
                    total=config.MAX_EPISODE_STEPS,
                    frame=observation["pixels"]["top"].copy(),
                    state=observation["agent_pos"].astype(np.float32).copy(),
                    action=None,
                    reward=max_reward,
                    phase=phase_for_reward(max_reward),
                    policy_call=policy_calls,
                    chunk_index=0,
                    inference_s=inference_seconds[-1] if inference_seconds else 0.0,
                    done=True,
                    success=success,
                    aborted=aborted,
                )
            )
    finally:
        env.close()

    return RolloutResult(
        seed=seed,
        execution_horizon=execution_horizon,
        success=success,
        aborted=aborted,
        steps=steps,
        policy_calls=policy_calls,
        max_reward=max_reward,
        sum_reward=sum_reward,
        elapsed_s=time.perf_counter() - started,
        inference_seconds=tuple(inference_seconds),
    )
