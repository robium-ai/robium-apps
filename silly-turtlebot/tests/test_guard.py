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

    rejected = [
        ("publish_cmd_vel", {"linear_x": 1.0}),
        ("navigate_to_location", {"location": "the moon"}),
        ("move_forward", {"distance_m": MAX_FORWARD_DISTANCE_M + 0.1}),
        ("look_around", {"quarter_turns": 5}),
        ("approach_object", {"object_id": "sock-1", "stand_off_m": 0.2}),
        ("approach_object", {"object_id": "invented-7", "stand_off_m": 1.0}),
        ("speak", {"message": "x" * (MAX_SPEECH_CHARS + 1)}),
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
