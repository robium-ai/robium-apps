from pathlib import Path
from threading import Event, Thread

import pytest

from vla_pick_and_place.rollout import (
    DeterministicFakePolicy,
    FixtureEnvironment,
    RolloutBusyError,
    RolloutRunner,
)

FIXTURES = Path(__file__).parents[1] / "test-assets" / "fixtures"


def make_runner(*, success: bool = True, steps: int = 4) -> RolloutRunner:
    return RolloutRunner(
        environment=FixtureEnvironment(FIXTURES, success=success, episode_steps=steps),
        policy=DeterministicFakePolicy(),
        max_steps=10,
    )


@pytest.mark.parametrize("success", [True, False])
def test_fake_rollout_uses_simulator_result_and_streams_nonblank_frames(success):
    events = []
    result = make_runner(success=success).run(
        0, "put the bowl on the plate", events.append
    )

    frames = [event.frame for event in events if event.frame is not None]
    assert result.success is success
    assert result.cancelled is False
    assert result.steps == 4
    assert frames
    assert all(frame.getbbox() is not None for frame in frames)


def test_one_rollout_lock_and_cooperative_cancellation():
    entered = Event()
    release = Event()
    runner = make_runner(steps=50)

    def on_event(event):
        if event.step == 1:
            entered.set()
            release.wait(timeout=2)

    thread = Thread(
        target=lambda: runner.run(0, "put the bowl on the plate", on_event),
        daemon=True,
    )
    thread.start()
    assert entered.wait(timeout=2)

    with pytest.raises(RolloutBusyError):
        runner.run(1, "put the bowl on the plate")

    runner.cancel()
    release.set()
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert runner.last_result is not None
    assert runner.last_result.cancelled is True
    assert runner.last_result.success is None
