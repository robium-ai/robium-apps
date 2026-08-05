"""Shape-variant env tests — geometry + coverage stay well-defined per shape."""

import gymnasium as gym
import numpy as np
import pytest

from imitation_manipulation import shapes


def test_shape_catalog():
    assert list(shapes.SHAPES) == ["T", "L", "I", "Z"]
    for rects in shapes.SHAPES.values():
        assert len(rects) >= 1
        for rect in rects:
            assert len(rect) == 4  # convex quads only


def test_t_matches_upstream_geometry():
    # T must reproduce gym-pusht's add_tee exactly (scale=30, length=4):
    # policy inputs are pixels — any drift here silently shifts the
    # training distribution.
    bar, stem = shapes.SHAPES["T"]
    assert bar == [(-60, 30), (60, 30), (60, 0), (-60, 0)]
    assert stem == [(-15, 30), (-15, 120), (15, 120), (15, 30)]


@pytest.mark.parametrize("shape", ["T", "L", "I", "Z"])
def test_env_steps_and_coverage(shape):
    env = gym.make(
        shapes.ENV_ID, shape=shape, obs_type="pixels_agent_pos", render_mode="rgb_array"
    )
    obs, _ = env.reset(seed=0)
    assert obs["pixels"].shape == (96, 96, 3)
    obs, reward, terminated, truncated, info = env.step(np.array([256.0, 256.0]))
    assert 0.0 <= info["coverage"] <= 1.0
    assert 0.0 <= reward <= 1.0
    env.close()


def test_unknown_shape_rejected():
    with pytest.raises(Exception, match="unknown shape"):
        gym.make(shapes.ENV_ID, shape="X")
