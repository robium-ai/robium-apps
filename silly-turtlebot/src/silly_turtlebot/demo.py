"""Deterministic first-slice mission with the same guarded tools as live mode."""

from __future__ import annotations

from .fake_robot import FakeRobot
from .guard import MissionGuard


def run_mock_sock_mission() -> MissionGuard:
    robot = FakeRobot()
    guard = MissionGuard(robot)

    script = (
        ("navigate_to_location", {"location": "living_room"}),
        ("look_around", {"quarter_turns": 4}),
        ("approach_object", {"object_id": "sock-1", "stand_off_m": 0.9}),
        (
            "speak",
            {"message": "A rogue sock. Fascinating. Unfortunately, I'm in management."},
        ),
        ("face_nearest_person", {}),
        ("speak", {"message": "Was this your contribution? I decline custody."}),
    )

    print("MODE: MOCK (no Gemini request, ROS node, Nav2 action, or motor command)")
    print('Human: "Patrol the living room and report any mess."')
    for name, arguments in script:
        result = guard.execute(name, arguments)
        print(f"[tool] {name}({arguments}) -> {result['status']}")
        if name == "speak":
            print(f"Robot: {arguments['message']}")
    print(f"[mock] mission complete: {len(guard.events)} guarded actions")
    return guard
