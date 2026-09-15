"""Semantic action guard between a generative model and a robot adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .config import (
    KNOWN_LOCATIONS,
    MAX_FORWARD_DISTANCE_M,
    MAX_ANGULAR_SPEED_RAD_S,
    MAX_LINEAR_SPEED_MPS,
    MAX_MOVE_DISTANCE_M,
    MAX_MOVE_DURATION_S,
    MAX_QUARTER_TURNS,
    MAX_ROTATION_DEG,
    MAX_SPEECH_CHARS,
    MAX_STAND_OFF_M,
    MIN_FORWARD_DISTANCE_M,
    MIN_STAND_OFF_M,
)


class GuardRejected(ValueError):
    """Raised when a model request is outside the semantic action contract."""


class RobotAdapter(Protocol):
    def health(self) -> dict[str, Any]: ...

    def navigate_to_location(self, location: str) -> dict[str, Any]: ...

    def move_forward(self, distance_m: float) -> dict[str, Any]: ...

    def move_distance(self, distance_m: float, speed_mps: float) -> dict[str, Any]: ...

    def rotate_by(self, angle_deg: float) -> dict[str, Any]: ...

    def move_for_duration(
        self, linear_mps: float, angular_rad_s: float, duration_s: float
    ) -> dict[str, Any]: ...

    def look_around(self, quarter_turns: int) -> dict[str, Any]: ...

    def approach_object(self, object_id: str, stand_off_m: float) -> dict[str, Any]: ...

    def face_nearest_person(self) -> dict[str, Any]: ...

    def dock(self) -> dict[str, Any]: ...

    def undock(self) -> dict[str, Any]: ...

    def speak(self, message: str) -> dict[str, Any]: ...

    def stop(self, reason: str) -> dict[str, Any]: ...


@dataclass(frozen=True)
class GuardEvent:
    name: str
    arguments: dict[str, Any]
    result: dict[str, Any]


@dataclass
class MissionGuard:
    adapter: RobotAdapter
    events: list[GuardEvent] = field(default_factory=list)
    grounded_object_ids: set[str] = field(default_factory=set)

    @property
    def allowed_tools(self) -> tuple[str, ...]:
        return (
            "get_robot_state",
            "move_distance",
            "rotate_by",
            "move_for_duration",
            "navigate_to_location",
            "move_forward",
            "look_around",
            "approach_object",
            "face_nearest_person",
            "dock",
            "undock",
            "speak",
            "stop",
            "ack",
            "complete_task",
        )

    def execute(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        args = dict(arguments or {})
        if name not in self.allowed_tools:
            raise GuardRejected(f"tool is not allowed: {name}")

        validated = self._validate(name, args)
        if name == "get_robot_state":
            result = {"status": "succeeded", "robot": self.adapter.health()}
        elif name == "ack":
            result = {"status": "succeeded", "ack": validated["status"]}
        elif name == "complete_task":
            result = {"status": "succeeded", "summary": validated["summary"]}
        else:
            method = getattr(self.adapter, name)
            result = method(**validated)
        if name in {
            "navigate_to_location",
            "move_forward",
            "move_distance",
            "move_for_duration",
            "dock",
            "undock",
        }:
            self.grounded_object_ids.clear()
        elif name == "look_around" and result.get("status") == "succeeded":
            self.grounded_object_ids = {
                item["object_id"]
                for item in result.get("visible_objects", [])
                if isinstance(item, dict)
                and isinstance(item.get("object_id"), str)
                and item["object_id"]
            }
        event = GuardEvent(name=name, arguments=validated, result=result)
        self.events.append(event)
        return result

    def _validate(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        validators = {
            "get_robot_state": self._no_args,
            "navigate_to_location": self._navigation_args,
            "move_forward": self._move_forward_args,
            "move_distance": self._move_distance_args,
            "rotate_by": self._rotate_args,
            "move_for_duration": self._timed_move_args,
            "look_around": self._look_args,
            "approach_object": self._approach_args,
            "face_nearest_person": self._no_args,
            "dock": self._no_args,
            "undock": self._no_args,
            "speak": self._speech_args,
            "stop": self._stop_args,
            "ack": self._status_args,
            "complete_task": self._summary_args,
        }
        return validators[name](args)

    @staticmethod
    def _exact_args(args: dict[str, Any], expected: set[str]) -> None:
        received = set(args)
        if received != expected:
            raise GuardRejected(
                f"expected arguments {sorted(expected)}, received {sorted(received)}"
            )

    def _navigation_args(self, args: dict[str, Any]) -> dict[str, Any]:
        self._exact_args(args, {"location"})
        location = args["location"]
        if not isinstance(location, str) or location not in KNOWN_LOCATIONS:
            raise GuardRejected(f"unknown location: {location!r}")
        return {"location": location}

    def _look_args(self, args: dict[str, Any]) -> dict[str, Any]:
        self._exact_args(args, {"quarter_turns"})
        turns = args["quarter_turns"]
        if isinstance(turns, bool) or not isinstance(turns, int):
            raise GuardRejected("quarter_turns must be an integer")
        if not 1 <= turns <= MAX_QUARTER_TURNS:
            raise GuardRejected(
                f"quarter_turns must be between 1 and {MAX_QUARTER_TURNS}"
            )
        return {"quarter_turns": turns}

    def _move_forward_args(self, args: dict[str, Any]) -> dict[str, Any]:
        self._exact_args(args, {"distance_m"})
        distance = args["distance_m"]
        if isinstance(distance, bool) or not isinstance(distance, (int, float)):
            raise GuardRejected("distance_m must be numeric")
        distance = float(distance)
        if not MIN_FORWARD_DISTANCE_M <= distance <= MAX_FORWARD_DISTANCE_M:
            raise GuardRejected(
                "distance_m must be between "
                f"{MIN_FORWARD_DISTANCE_M} and {MAX_FORWARD_DISTANCE_M}"
            )
        return {"distance_m": distance}

    @staticmethod
    def _number(value: Any, field: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise GuardRejected(f"{field} must be numeric")
        value = float(value)
        if value != value or value in {float("inf"), float("-inf")}:
            raise GuardRejected(f"{field} must be finite")
        return value

    def _move_distance_args(self, args: dict[str, Any]) -> dict[str, Any]:
        self._exact_args(args, {"distance_m", "speed_mps"})
        distance = self._number(args["distance_m"], "distance_m")
        speed = self._number(args["speed_mps"], "speed_mps")
        if abs(distance) < MIN_FORWARD_DISTANCE_M or abs(distance) > MAX_MOVE_DISTANCE_M:
            raise GuardRejected(
                f"absolute distance_m must be between {MIN_FORWARD_DISTANCE_M} and {MAX_MOVE_DISTANCE_M}"
            )
        if not 0.05 <= speed <= MAX_LINEAR_SPEED_MPS:
            raise GuardRejected(
                f"speed_mps must be between 0.05 and {MAX_LINEAR_SPEED_MPS}"
            )
        return {"distance_m": distance, "speed_mps": speed}

    def _rotate_args(self, args: dict[str, Any]) -> dict[str, Any]:
        self._exact_args(args, {"angle_deg"})
        angle = self._number(args["angle_deg"], "angle_deg")
        if abs(angle) < 1.0 or abs(angle) > MAX_ROTATION_DEG:
            raise GuardRejected(f"absolute angle_deg must be between 1 and {MAX_ROTATION_DEG}")
        return {"angle_deg": angle}

    def _timed_move_args(self, args: dict[str, Any]) -> dict[str, Any]:
        self._exact_args(args, {"linear_mps", "angular_rad_s", "duration_s"})
        linear = self._number(args["linear_mps"], "linear_mps")
        angular = self._number(args["angular_rad_s"], "angular_rad_s")
        duration = self._number(args["duration_s"], "duration_s")
        if abs(linear) > MAX_LINEAR_SPEED_MPS:
            raise GuardRejected(f"absolute linear_mps must not exceed {MAX_LINEAR_SPEED_MPS}")
        if abs(angular) > MAX_ANGULAR_SPEED_RAD_S:
            raise GuardRejected(
                f"absolute angular_rad_s must not exceed {MAX_ANGULAR_SPEED_RAD_S}"
            )
        if linear == 0.0 and angular == 0.0:
            raise GuardRejected("linear_mps and angular_rad_s cannot both be zero")
        if not 0.1 <= duration <= MAX_MOVE_DURATION_S:
            raise GuardRejected(f"duration_s must be between 0.1 and {MAX_MOVE_DURATION_S}")
        return {
            "linear_mps": linear,
            "angular_rad_s": angular,
            "duration_s": duration,
        }

    def _bounded_text(self, args: dict[str, Any], field: str) -> dict[str, Any]:
        self._exact_args(args, {field})
        value = args[field]
        if not isinstance(value, str) or not value.strip():
            raise GuardRejected(f"{field} must be non-empty")
        return {field: value.strip()[:MAX_SPEECH_CHARS]}

    def _status_args(self, args: dict[str, Any]) -> dict[str, Any]:
        return self._bounded_text(args, "status")

    def _summary_args(self, args: dict[str, Any]) -> dict[str, Any]:
        return self._bounded_text(args, "summary")

    def _approach_args(self, args: dict[str, Any]) -> dict[str, Any]:
        self._exact_args(args, {"object_id", "stand_off_m"})
        object_id = args["object_id"]
        if not isinstance(object_id, str) or not object_id.strip():
            raise GuardRejected("object_id must be a non-empty adapter-issued ID")
        if object_id not in self.grounded_object_ids:
            raise GuardRejected(
                f"object_id was not grounded by the latest scan: {object_id!r}"
            )
        distance = args["stand_off_m"]
        if isinstance(distance, bool) or not isinstance(distance, (int, float)):
            raise GuardRejected("stand_off_m must be numeric")
        distance = float(distance)
        if not MIN_STAND_OFF_M <= distance <= MAX_STAND_OFF_M:
            raise GuardRejected(
                f"stand_off_m must be between {MIN_STAND_OFF_M} and {MAX_STAND_OFF_M}"
            )
        return {"object_id": object_id, "stand_off_m": distance}

    def _no_args(self, args: dict[str, Any]) -> dict[str, Any]:
        self._exact_args(args, set())
        return {}

    def _speech_args(self, args: dict[str, Any]) -> dict[str, Any]:
        self._exact_args(args, {"message"})
        message = args["message"]
        if not isinstance(message, str) or not message.strip():
            raise GuardRejected("message must be non-empty")
        message = message.strip()
        if len(message) > MAX_SPEECH_CHARS:
            raise GuardRejected(f"message exceeds {MAX_SPEECH_CHARS} characters")
        return {"message": message}

    def _stop_args(self, args: dict[str, Any]) -> dict[str, Any]:
        self._exact_args(args, {"reason"})
        reason = args["reason"]
        if not isinstance(reason, str) or not reason.strip():
            raise GuardRejected("stop reason must be non-empty")
        return {"reason": reason.strip()[:MAX_SPEECH_CHARS]}
