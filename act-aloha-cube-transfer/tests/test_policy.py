import numpy as np
import pytest

from act_aloha_cube_transfer import config
from act_aloha_cube_transfer.checkpoint import ensure_official_checkpoint
from act_aloha_cube_transfer.environment import make_env
from act_aloha_cube_transfer.policy import ACTCheckpoint


@pytest.mark.slow
def test_official_policy_predicts_complete_finite_chunk_on_cpu():
    checkpoint = ACTCheckpoint(ensure_official_checkpoint(), device="cpu")
    env = make_env()
    try:
        observation, _ = env.reset(seed=1000)
        actions = checkpoint.predict_chunk(observation)
    finally:
        env.close()
    assert actions.shape == (config.ACTION_CHUNK_SIZE, 14)
    assert np.isfinite(actions).all()
