"""Deterministic first-slice mission with the same guarded tools as live mode."""

from __future__ import annotations

from .fake_robot import FakeRobot
from .guard import MissionGuard


def run_mock_navigation_mission() -> MissionGuard:
    robot = FakeRobot()
    guard = MissionGuard(robot)

    script = (
        ("get_robot_state", {}),
        ("undock", {}),
        ("rotate_by", {"angle_deg": 30.0}),
        ("move_distance", {"distance_m": 0.4, "speed_mps": 0.15}),
        (
            "move_for_duration",
            {"linear_mps": 0.1, "angular_rad_s": 0.2, "duration_s": 1.0},
        ),
        ("ack", {"status": "Mock motion sequence finished."}),
        ("complete_task", {"summary": "Mock navigation mission complete."}),
    )

    print("MODE: MOCK (no Gemini request, ROS node, Nav2 action, or motor command)")
    print('Human: "Undock, rotate 30 degrees, then move forward in a gentle arc."')
    for name, arguments in script:
        result = guard.execute(name, arguments)
        print(f"[tool] {name}({arguments}) -> {result['status']}")
    print(f"[mock] mission complete: {len(guard.events)} guarded actions")
    return guard
