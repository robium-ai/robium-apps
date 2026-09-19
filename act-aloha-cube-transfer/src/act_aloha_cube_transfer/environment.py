"""The exact ALOHA simulator contract used by the official ACT policy."""

from __future__ import annotations

import gymnasium as gym
import numpy as np

import gym_aloha  # noqa: F401 - importing registers the environments

from act_aloha_cube_transfer import config


JOINT_CONTROLS = (
    ("Left waist", -3.14158, 3.14158, 0.0),
    ("Left shoulder", -1.85005, 1.25664, -0.96),
    ("Left elbow", -1.76278, 1.60570, 1.16),
    ("Left forearm roll", -3.14158, 3.14158, 0.0),
    ("Left wrist angle", -1.86750, 2.23402, -0.3),
    ("Left wrist rotate", -3.14158, 3.14158, 0.0),
    ("Left gripper", 0.0, 1.0, 0.1),
    ("Right waist", -3.14158, 3.14158, 0.0),
    ("Right shoulder", -1.85005, 1.25664, -0.96),
    ("Right elbow", -1.76278, 1.60570, 1.16),
    ("Right forearm roll", -3.14158, 3.14158, 0.0),
    ("Right wrist angle", -1.86750, 2.23402, -0.3),
    ("Right wrist rotate", -3.14158, 3.14158, 0.0),
    ("Right gripper", 0.0, 1.0, 0.1),
)

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


def validate_joint_targets(values) -> np.ndarray:
    targets = np.asarray(values, dtype=np.float32)
    if targets.shape != (len(JOINT_CONTROLS),):
        raise ValueError(f"manual pose must contain {len(JOINT_CONTROLS)} joint targets")
    if not np.isfinite(targets).all():
        raise ValueError("manual joint targets must be finite")
    for target, (label, lower, upper, _default) in zip(targets, JOINT_CONTROLS, strict=True):
        if not lower <= float(target) <= upper:
            raise ValueError(f"{label} target {target:.3f} is outside [{lower:.3f}, {upper:.3f}]")
    return targets


def step_manual_physics(env, values) -> np.ndarray:
    """Advance one 50 Hz control step without rendering observation cameras."""
    targets = validate_joint_targets(values)
    inner = env.unwrapped._env
    inner.task.before_step(targets, inner.physics)
    inner.physics.step(inner._n_sub_steps)
    inner.task.after_step(inner.physics)
    return inner.task.get_qpos(inner.physics)


def render_top_frame(env) -> np.ndarray:
    """Render only the camera displayed by the manual-control workspace."""
    inner = env.unwrapped._env
    return inner.physics.render(height=480, width=640, camera_id="top")
