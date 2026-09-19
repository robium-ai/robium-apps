import base64
import re
import time

import numpy as np
import pytest

from act_aloha_cube_transfer.demo.episode_runner import ManualController
from act_aloha_cube_transfer.demo.ui import frame_html
from act_aloha_cube_transfer.environment import JOINT_CONTROLS


def test_live_frame_is_complete_inline_jpeg():
    frame = np.full((480, 640, 3), 127, dtype=np.uint8)
    payload = frame_html(frame)
    assert "MuJoCo simulator" in payload
    match = re.search(r'data:image/jpeg;base64,([^\"]+)', payload)
    assert match
    decoded = base64.b64decode(match.group(1))
    assert decoded[:2] == b"\xff\xd8"
    assert decoded[-2:] == b"\xff\xd9"


def test_persistent_manual_controller_streams_at_30hz_and_accepts_live_targets():
    controller = ManualController()
    targets = [control[3] for control in JOINT_CONTROLS]
    controller.start(1001, targets)
    try:
        samples = [controller.next_frame(timeout=5) for _ in range(12)]
        timestamps = [sample[2] for sample in samples]
        measured_fps = (len(timestamps) - 1) / (timestamps[-1] - timestamps[0])
        assert measured_fps == pytest.approx(30.0, rel=0.15)

        targets[0] = 0.5
        controller.update(1001, targets)
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            _frame, state, _timestamp = controller.next_frame(timeout=1)
            if abs(float(state[0]) - 0.5) < 0.04:
                break
        assert state[0] == pytest.approx(0.5, abs=0.04)
    finally:
        controller.stop()
    assert not controller.running
