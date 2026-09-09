"""Semantic action guard between a generative model and a robot adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .config import (
    KNOWN_LOCATIONS,
    MAX_FORWARD_DISTANCE_M,
    MAX_QUARTER_TURNS,
    MAX_SPEECH_CHARS,
    MAX_STAND_OFF_M,
    MIN_FORWARD_DISTANCE_M,
    MIN_STAND_OFF_M,
)


class GuardRejected(ValueError):
    """Raised when a model request is outside the semantic action contract."""


class RobotAdapter(Protocol):
    def navigate_to_location(self, location: str) -> dict[str, Any]: ...

    def move_forward(self, distance_m: float) -> dict[str, Any]: ...

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
            "navigate_to_location",
            "move_forward",
            "look_around",
            "approach_object",
            "face_nearest_person",
            "dock",
            "undock",
            "speak",
            "stop",
        )

    def execute(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        args = dict(arguments or {})
        if name not in self.allowed_tools:
            raise GuardRejected(f"tool is not allowed: {name}")

        validated = self._validate(name, args)
        method = getattr(self.adapter, name)
        result = method(**validated)
        if name in {"navigate_to_location", "move_forward", "dock", "undock"}:
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
            "navigate_to_location": self._navigation_args,
            "move_forward": self._move_forward_args,
            "look_around": self._look_args,
            "approach_object": self._approach_args,
            "face_nearest_person": self._no_args,
            "dock": self._no_args,
            "undock": self._no_args,
            "speak": self._speech_args,
            "stop": self._stop_args,
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
