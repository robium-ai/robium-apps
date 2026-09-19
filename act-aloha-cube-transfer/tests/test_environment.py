import hashlib

import numpy as np

import pytest

from act_aloha_cube_transfer.environment import (
    JOINT_CONTROLS,
    make_env,
    render_top_frame,
    step_manual_physics,
    validate_joint_targets,
    validate_observation,
)


def test_aloha_environment_contract_and_seeded_state():
    env = make_env()
    try:
        first, _ = env.reset(seed=1000)
        validate_observation(first)
        first_state = first["agent_pos"].copy()
        first_frame = hashlib.sha256(first["pixels"]["top"].tobytes()).hexdigest()

        second, _ = env.reset(seed=1000)
        validate_observation(second)
        assert np.array_equal(first_state, second["agent_pos"])
        assert first_frame == hashlib.sha256(second["pixels"]["top"].tobytes()).hexdigest()
        assert env.action_space.shape == (14,)

        observation, reward, terminated, truncated, info = env.step(np.zeros(14, dtype=np.float32))
        validate_observation(observation)
        assert float(observation["pixels"]["top"].std()) > 1.0
        assert float(reward) >= 0.0
        assert not terminated
        assert not truncated
        assert "is_success" in info
    finally:
        env.close()


def test_manual_joint_controls_name_both_arms_and_validate_ranges():
    assert len(JOINT_CONTROLS) == 14
    assert [control[0] for control in JOINT_CONTROLS[:2]] == ["Left waist", "Left shoulder"]
    assert [control[0] for control in JOINT_CONTROLS[-2:]] == ["Right wrist rotate", "Right gripper"]

    defaults = [control[3] for control in JOINT_CONTROLS]
    assert np.array_equal(validate_joint_targets(defaults), np.asarray(defaults, dtype=np.float32))

    invalid = defaults.copy()
    invalid[0] = JOINT_CONTROLS[0][2] + 0.1
    with pytest.raises(ValueError, match="Left waist"):
        validate_joint_targets(invalid)


def test_manual_physics_moves_named_joint_without_observation_rendering():
    targets = [control[3] for control in JOINT_CONTROLS]
    targets[0] = 0.5
    env = make_env()
    try:
        env.reset(seed=1001)
        for _ in range(10):
            realized = step_manual_physics(env, targets)
        frame = render_top_frame(env)
        assert frame.shape == (480, 640, 3)
        assert frame.dtype == np.uint8
        assert realized.shape == (14,)
        assert realized[0] == pytest.approx(0.5, abs=0.04)
    finally:
        env.close()
