from pathlib import Path
from threading import Event, Thread

from vla_pick_and_place.rollout import (
    DeterministicFakePolicy,
    FixtureEnvironment,
    RolloutRunner,
)
from vla_pick_and_place.ui import stream_rollout


def test_ui_generator_streams_frames_and_returns_measured_result():
    fixture_dir = Path(__file__).parents[1] / "test-assets" / "fixtures"
    runner = RolloutRunner(FixtureEnvironment(fixture_dir), DeterministicFakePolicy())

    updates = list(
        stream_rollout(runner, "Official fixed state 0", "put the bowl on the plate")
    )

    assert len(updates) >= 2
    assert updates[0][1]["phase"] == "starting"
    assert updates[1][0].getbbox() is not None
    assert updates[-1][1]["success"] is True
    assert updates[-1][1]["frame_count"] == 5


def test_ui_duplicate_rollout_returns_readable_busy_state():
    fixture_dir = Path(__file__).parents[1] / "test-assets" / "fixtures"
    runner = RolloutRunner(
        FixtureEnvironment(fixture_dir, episode_steps=50), DeterministicFakePolicy()
    )
    entered = Event()
    release = Event()

    def block_first_rollout(event):
        if event.step == 1:
            entered.set()
            release.wait(timeout=2)

    first = Thread(
        target=lambda: runner.run(0, "put the bowl on the plate", block_first_rollout),
        daemon=True,
    )
    first.start()
    assert entered.wait(timeout=2)

    updates = list(
        stream_rollout(runner, "Official fixed state 1", "put the bowl on the plate")
    )
    assert updates[-1][1] == {
        "phase": "busy",
        "message": "A rollout is already running. Wait for it to finish or cancel it, then retry.",
    }

    runner.cancel()
    release.set()
    first.join(timeout=2)
