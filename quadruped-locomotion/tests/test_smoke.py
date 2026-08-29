"""Real-platform smoke: train briefly and require a newly written checkpoint."""

import pytest

from go2_locomotion import config
from go2_locomotion.run import doctor, run_command


@pytest.mark.gpu
def test_smoke_train_writes_checkpoint():
    assert doctor() == 0, "GPU/Isaac Lab preflight failed; this is not a passing smoke"
    before = config.checkpoints()
    assert run_command(config.train_cmd("smoke")) == 0
    created = config.checkpoints() - before
    assert created, f"training succeeded but wrote no new checkpoint below {config.LOG_ROOT}"
