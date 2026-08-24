from pathlib import Path

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
    assert updates[0][0].getbbox() is not None
    assert updates[-1][1]["success"] is True
    assert updates[-1][1]["frame_count"] == 5
