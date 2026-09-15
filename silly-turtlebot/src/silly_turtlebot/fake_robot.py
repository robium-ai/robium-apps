"""Transparent, deterministic fake robot used by the first working slice."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeRobot:
    location: str = "dock"
    known_objects: dict[str, dict[str, Any]] = field(
        default_factory=lambda: {
            "sock-1": {
                "label": "blue sock",
                "location": "living_room",
                "confidence": 0.97,
            }
        }
    )
    spoken: list[str] = field(default_factory=list)
    forward_distance_m: float = 0.0
    stopped: bool = False
    is_docked: bool = True
    battery_percentage: float = 82.0

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "is_docked": self.is_docked,
            "battery_percentage": self.battery_percentage,
            "motion": {"state": "idle"},
            "odometry": {"frame_id": "odom", "x": self.forward_distance_m},
            "cameras": {
                "primary": {
                    "fresh": True,
                    "width": 640,
                    "height": 360,
                    "horizontal_fov_deg": 69.0,
                    "vertical_fov_deg": 42.0,
                }
            },
        }

    def navigate_to_location(self, location: str) -> dict[str, Any]:
        self.location = location
        return {"status": "succeeded", "location": location, "mode": "mock"}

    def look_around(self, quarter_turns: int) -> dict[str, Any]:
        visible = [
            {"object_id": object_id, **details}
            for object_id, details in self.known_objects.items()
            if details["location"] == self.location
        ]
        return {
            "status": "succeeded",
            "quarter_turns": quarter_turns,
            "visible_objects": visible,
            "mode": "mock",
        }

    def move_forward(self, distance_m: float) -> dict[str, Any]:
        self.forward_distance_m += distance_m
        return {
            "status": "succeeded",
            "distance_m": distance_m,
            "mode": "mock",
        }

    def move_distance(self, distance_m: float, speed_mps: float) -> dict[str, Any]:
        self.forward_distance_m += distance_m
        return {
            "status": "succeeded",
            "distance_m": distance_m,
            "speed_mps": speed_mps,
            "mode": "mock",
        }

    def rotate_by(self, angle_deg: float) -> dict[str, Any]:
        return {"status": "succeeded", "angle_deg": angle_deg, "mode": "mock"}

    def move_for_duration(
        self, linear_mps: float, angular_rad_s: float, duration_s: float
    ) -> dict[str, Any]:
        self.forward_distance_m += linear_mps * duration_s
        return {
            "status": "succeeded",
            "linear_mps": linear_mps,
            "angular_rad_s": angular_rad_s,
            "duration_s": duration_s,
            "mode": "mock",
        }

    def approach_object(self, object_id: str, stand_off_m: float) -> dict[str, Any]:
        target = self.known_objects.get(object_id)
        if target is None:
            return {"status": "rejected", "reason": "unknown_object", "mode": "mock"}
        if target["location"] != self.location:
            return {
                "status": "rejected",
                "reason": "object_not_visible",
                "mode": "mock",
            }
        return {
            "status": "succeeded",
            "object_id": object_id,
            "stand_off_m": stand_off_m,
            "mode": "mock",
        }

    def face_nearest_person(self) -> dict[str, Any]:
        return {"status": "succeeded", "person": "volunteer-1", "mode": "mock"}

    def dock(self) -> dict[str, Any]:
        self.is_docked = True
        self.location = "dock"
        return {"status": "succeeded", "is_docked": True, "mode": "mock"}

    def undock(self) -> dict[str, Any]:
        self.is_docked = False
        return {"status": "succeeded", "is_docked": False, "mode": "mock"}

    def speak(self, message: str) -> dict[str, Any]:
        self.spoken.append(message)
        return {"status": "succeeded", "message": message, "mode": "mock"}

    def stop(self, reason: str) -> dict[str, Any]:
        self.stopped = True
        return {"status": "succeeded", "reason": reason, "mode": "mock"}
