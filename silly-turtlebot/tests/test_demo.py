from silly_turtlebot.demo import run_mock_navigation_mission
from silly_turtlebot.fake_robot import FakeRobot


def test_mock_navigation_mission_uses_expected_guarded_sequence() -> None:
    guard = run_mock_navigation_mission()

    assert [event.name for event in guard.events] == [
        "get_robot_state",
        "undock",
        "rotate_by",
        "move_distance",
        "move_for_duration",
        "ack",
        "complete_task",
    ]
    robot = guard.adapter
    assert isinstance(robot, FakeRobot)
    assert robot.is_docked is False
    assert robot.forward_distance_m == 0.5
    assert robot.spoken == []
