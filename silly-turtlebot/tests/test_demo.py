from silly_turtlebot.demo import run_mock_sock_mission
from silly_turtlebot.fake_robot import FakeRobot


def test_mock_sock_mission_uses_expected_guarded_sequence() -> None:
    guard = run_mock_sock_mission()

    assert [event.name for event in guard.events] == [
        "navigate_to_location",
        "look_around",
        "approach_object",
        "speak",
        "face_nearest_person",
        "speak",
    ]
    robot = guard.adapter
    assert isinstance(robot, FakeRobot)
    assert robot.location == "living_room"
    assert len(robot.spoken) == 2
