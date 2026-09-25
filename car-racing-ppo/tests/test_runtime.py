import numpy as np

from car_racing_ppo.runtime import (
    FRAME_SKIP,
    MODEL_REVISION,
    MODEL_SHA256,
    make_vec_env,
)


def test_checkpoint_is_immutably_pinned():
    assert len(MODEL_REVISION) == 40
    assert len(MODEL_SHA256) == 64


def test_preprocessing_matches_checkpoint_shape():
    env = make_vec_env("rgb_array", seed=3)
    try:
        observation = env.reset()
        assert observation.shape == (1, 2, 64, 64)
        action = np.array([[0.0, 0.0, 0.0]], dtype=np.float32)
        observation, _, _, _ = env.step(action)
        assert observation.shape == (1, 2, 64, 64)
    finally:
        env.close()


def test_frame_skip_constant_matches_published_config():
    assert FRAME_SKIP == 2
