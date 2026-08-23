import pytest

from act_aloha_cube_transfer.checkpoint import ensure_official_checkpoint
from act_aloha_cube_transfer.policy import ACTCheckpoint
from act_aloha_cube_transfer.rollout import run_rollout


@pytest.mark.slow
def test_real_policy_replans_and_cancels_cleanly():
    checkpoint = ACTCheckpoint(ensure_official_checkpoint(), device="cpu")
    observed_steps = 0

    def count_steps(event):
        nonlocal observed_steps
        if event.action is not None:
            observed_steps += 1

    result = run_rollout(
        checkpoint,
        seed=1000,
        execution_horizon=25,
        on_step=count_steps,
        should_abort=lambda: observed_steps >= 26,
    )
    assert result.aborted
    assert result.steps == 26
    assert result.policy_calls == 2
    assert len(result.inference_seconds) == 2
    assert all(value > 0 for value in result.inference_seconds)
