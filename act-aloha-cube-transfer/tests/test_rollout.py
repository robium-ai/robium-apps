import numpy as np
import pytest

from act_aloha_cube_transfer.rollout import run_rollout


def observation(step: int = 0):
    frame = np.full((480, 640, 3), step % 255, dtype=np.uint8)
    return {"pixels": {"top": frame}, "agent_pos": np.zeros(14)}


class FakePolicy:
    def __init__(self):
        self.calls = 0

    def reset(self):
        self.calls = 0

    def predict_chunk(self, _observation):
        self.calls += 1
        return np.full((100, 14), self.calls, dtype=np.float32)


class FakeEnv:
    def __init__(self, truncate_at=60):
        self.steps = 0
        self.truncate_at = truncate_at
        self.closed = False

    def reset(self, seed):
        self.steps = 0
        return observation(), {"seed": seed}

    def step(self, action):
        self.steps += 1
        return observation(self.steps), 0.0, False, self.steps >= self.truncate_at, {"is_success": False}

    def close(self):
        self.closed = True


@pytest.mark.parametrize(("horizon", "calls"), ((25, 3), (50, 2), (100, 1)))
def test_execution_horizon_controls_replanning_boundaries(horizon, calls):
    policy = FakePolicy()
    events = []
    result = run_rollout(
        policy,
        seed=7,
        execution_horizon=horizon,
        on_step=events.append,
        env_factory=lambda: FakeEnv(),
    )
    assert result.steps == 60
    assert result.policy_calls == calls
    assert policy.calls == calls
    assert events[1].policy_call == 1
    if horizon < 60:
        assert events[horizon + 1].chunk_index == 0
        assert events[horizon + 1].policy_call == 2
    assert events[-1].done


def test_rollout_cancels_between_actions_and_closes_environment():
    policy = FakePolicy()
    env = FakeEnv(truncate_at=300)
    events = []
    result = run_rollout(
        policy,
        seed=9,
        execution_horizon=25,
        on_step=events.append,
        should_abort=lambda: len([event for event in events if event.action is not None]) >= 26,
        env_factory=lambda: env,
    )
    assert result.aborted
    assert result.steps == 26
    assert result.policy_calls == 2
    assert env.closed
    assert events[-1].done and events[-1].aborted
