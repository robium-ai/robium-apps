import hashlib

import numpy as np

from act_aloha_cube_transfer.environment import make_env, validate_observation


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
