import base64
import re

import numpy as np

from act_aloha_cube_transfer.demo.ui import evidence_markdown, frame_html


def test_live_frame_is_complete_inline_jpeg():
    frame = np.full((480, 640, 3), 127, dtype=np.uint8)
    payload = frame_html(frame)
    match = re.search(r'data:image/jpeg;base64,([^\"]+)', payload)
    assert match
    decoded = base64.b64decode(match.group(1))
    assert decoded[:2] == b"\xff\xd8"
    assert decoded[-2:] == b"\xff\xd9"


def test_evidence_copy_keeps_published_and_local_results_separate():
    markdown = evidence_markdown(
        {
            "published": {"episodes": 500, "success_rate": 0.83},
            "local": {
                "execution_horizon": 100,
                "selected_seed": 1001,
                "episodes": [{"success": True}, {"success": False}],
            },
        }
    )
    assert "published LeRobot evaluation" in markdown
    assert "local MPS" in markdown
    assert "separate experiments" in markdown
