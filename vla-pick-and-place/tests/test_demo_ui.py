"""Fast guards for the local demo workspace."""

from pathlib import Path

from vla_pick_and_place.demo.ui import (
    CONTROLLER_CHOICES,
    CONTROLLER_NOTE,
    _preview_recording,
)


def test_viewer_has_real_scene_data_before_the_first_episode():
    preview = _preview_recording()
    assert isinstance(preview, Path)
    assert preview.suffix == ".rrd"
    assert preview.stat().st_size > 1_000


def test_controller_copy_is_concise_and_result_focused():
    labels = [label for label, _value in CONTROLLER_CHOICES]
    assert labels == [
        "Scripted controller — task reference",
        "SmolVLA checkpoint — 100 steps",
    ]
    assert "Current checkpoint result: 0/10 successful evaluation episodes." in CONTROLLER_NOTE
    for phrase in ("honest", "magic", "flail", "theater", "correct result"):
        assert phrase not in CONTROLLER_NOTE.lower()
