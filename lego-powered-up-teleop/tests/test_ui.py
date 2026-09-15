from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from lego_powered_up_teleop.ui import action_for_robot, action_from_flags


def test_arrow_actions() -> None:
    assert action_from_flags(up=True, down=False, left=False, right=False) == (1.0, 0.0)
    assert action_from_flags(up=False, down=True, left=False, right=False) == (-1.0, 0.0)
    assert action_from_flags(up=False, down=False, left=True, right=False) == (0.0, -1.0)
    assert action_from_flags(up=False, down=False, left=False, right=True) == (0.0, 1.0)


def test_opposite_keys_cancel() -> None:
    assert action_from_flags(up=True, down=True, left=True, right=True) == (0.0, 0.0)


def test_stop_overrides_a_held_direction() -> None:
    assert action_from_flags(
        up=True, down=False, left=False, right=False, stop=True
    ) == (0.0, 0.0)


def test_robot_calibration_inverts_only_throttle() -> None:
    assert action_for_robot((1.0, 0.0)) == (-1.0, 0.0)
    assert action_for_robot((-1.0, 0.0)) == (1.0, 0.0)
    assert action_for_robot((0.0, -1.0)) == (0.0, -1.0)
    assert action_for_robot((0.0, 1.0)) == (0.0, 1.0)
