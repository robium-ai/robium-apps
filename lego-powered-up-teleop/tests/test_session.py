from __future__ import annotations

from lego_powered_up_teleop.session import DriveSession


def test_session_starts_at_zero_power() -> None:
    assert DriveSession().desired_wheels() == (0, 0)


def test_session_mixes_forward_and_right_arc() -> None:
    session = DriveSession()
    session.set_action(1.0, 0.5, 40)
    left, right = session.desired_wheels()
    assert left == 40
    assert 0 < right < left


def test_session_stop_action_is_immediately_zero() -> None:
    session = DriveSession()
    session.set_action(1.0, 0.0, 35)
    session.set_action(0.0, 0.0, 35)
    assert session.desired_wheels() == (0, 0)
