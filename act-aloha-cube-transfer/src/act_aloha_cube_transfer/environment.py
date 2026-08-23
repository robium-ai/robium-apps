"""The exact ALOHA simulator contract used by the official ACT policy."""

from __future__ import annotations

import gymnasium as gym
import numpy as np

import gym_aloha  # noqa: F401 - importing registers the environments

from act_aloha_cube_transfer import config


def make_env():
    return gym.make(
        config.ENV_ID,
        obs_type="pixels_agent_pos",
        render_mode="rgb_array",
    )


def validate_observation(observation: dict) -> None:
    try:
        top = observation["pixels"]["top"]
        state = observation["agent_pos"]
    except (KeyError, TypeError) as exc:
        raise ValueError("ALOHA observation must contain pixels.top and agent_pos") from exc
    if top.shape != (480, 640, 3) or top.dtype != np.uint8:
        raise ValueError(f"unexpected top camera contract: {top.shape}, {top.dtype}")
    if state.shape != (14,) or not np.isfinite(state).all():
        raise ValueError(f"unexpected robot state contract: {state.shape}")
