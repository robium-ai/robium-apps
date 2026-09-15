import pytest

from silly_turtlebot.config import MAX_FORWARD_DISTANCE_M, MAX_SPEECH_CHARS
from silly_turtlebot.fake_robot import FakeRobot
from silly_turtlebot.guard import GuardRejected, MissionGuard
from silly_turtlebot.tools import function_declarations


def test_guard_allows_grounded_actions_and_rejects_unsafe_authority() -> None:
    guard = MissionGuard(FakeRobot())
    guard.execute("navigate_to_location", {"location": "living_room"})
    assert guard.execute("move_forward", {"distance_m": 0.25})["status"] == "succeeded"
    guard.execute("look_around", {"quarter_turns": 1})
    assert (
        guard.execute("approach_object", {"object_id": "sock-1", "stand_off_m": 1.0})[
            "status"
        ]
        == "succeeded"
    )
    assert guard.execute("undock", {})["is_docked"] is False
    assert guard.execute("dock", {})["is_docked"] is True
    assert guard.execute("get_robot_state", {})["robot"]["motion"]["state"] == "idle"
    assert (
        guard.execute("move_distance", {"distance_m": -0.2, "speed_mps": 0.1})[
            "status"
        ]
        == "succeeded"
    )
    assert guard.execute("rotate_by", {"angle_deg": -30})["status"] == "succeeded"
    assert (
        guard.execute(
            "move_for_duration",
            {"linear_mps": 0.1, "angular_rad_s": 0.2, "duration_s": 1.0},
        )["status"]
        == "succeeded"
    )
    assert guard.execute("ack", {"status": "still observing"})["status"] == "succeeded"
    assert (
        guard.execute("complete_task", {"summary": "done"})["status"]
        == "succeeded"
    )

    rejected = [
        ("publish_cmd_vel", {"linear_x": 1.0}),
        ("navigate_to_location", {"location": "the moon"}),
        ("move_forward", {"distance_m": MAX_FORWARD_DISTANCE_M + 0.1}),
        ("move_distance", {"distance_m": 0.0, "speed_mps": 0.1}),
        (
            "move_for_duration",
            {"linear_mps": 0.0, "angular_rad_s": 0.0, "duration_s": 1.0},
        ),
        ("rotate_by", {"angle_deg": 0.0}),
        ("look_around", {"quarter_turns": 5}),
        ("approach_object", {"object_id": "sock-1", "stand_off_m": 0.2}),
        ("approach_object", {"object_id": "invented-7", "stand_off_m": 1.0}),
        ("speak", {"message": "x" * (MAX_SPEECH_CHARS + 1)}),
        ("dock", {"location": "dock"}),
    ]
    for name, arguments in rejected:
        with pytest.raises(GuardRejected):
            guard.execute(name, arguments)

    declarations = function_declarations()
    assert tuple(item["name"] for item in declarations) == guard.allowed_tools
    assert all(item["behavior"] == "BLOCKING" for item in declarations)
    serialized = repr(declarations).lower()
    assert all(
        forbidden not in serialized
        for forbidden in ("cmd_vel", "linear_x", "angular_z", "map_x", "map_y")
    )
