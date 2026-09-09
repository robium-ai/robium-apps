"""Gemini Live API function declarations for guarded robot actions."""

from __future__ import annotations

from typing import Any

from .config import (
    KNOWN_LOCATIONS,
    MAX_FORWARD_DISTANCE_M,
    MAX_QUARTER_TURNS,
    MAX_SPEECH_CHARS,
    MAX_STAND_OFF_M,
    MIN_FORWARD_DISTANCE_M,
    MIN_STAND_OFF_M,
)


def function_declarations() -> list[dict[str, Any]]:
    blocking = "BLOCKING"
    return [
        {
            "name": "navigate_to_location",
            "description": "Navigate with Nav2 to one configured named location.",
            "behavior": blocking,
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "location": {
                        "type": "STRING",
                        "enum": list(KNOWN_LOCATIONS),
                    }
                },
                "required": ["location"],
            },
        },
        {
            "name": "move_forward",
            "description": (
                "Move straight forward in the current heading using Nav2 collision "
                "checking. Use for requests such as go forward or move straight; "
                "use 0.25 meters when the person only says a little."
            ),
            "behavior": blocking,
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "distance_m": {
                        "type": "NUMBER",
                        "minimum": MIN_FORWARD_DISTANCE_M,
                        "maximum": MAX_FORWARD_DISTANCE_M,
                    }
                },
                "required": ["distance_m"],
            },
        },
        {
            "name": "look_around",
            "description": "Rotate in one to four bounded 90-degree increments to inspect a scene.",
            "behavior": blocking,
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "quarter_turns": {
                        "type": "INTEGER",
                        "minimum": 1,
                        "maximum": MAX_QUARTER_TURNS,
                    }
                },
                "required": ["quarter_turns"],
            },
        },
        {
            "name": "approach_object",
            "description": (
                "Approach an object already detected and grounded by the robot adapter. "
                "Never invent an object_id."
            ),
            "behavior": blocking,
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "object_id": {"type": "STRING"},
                    "stand_off_m": {
                        "type": "NUMBER",
                        "minimum": MIN_STAND_OFF_M,
                        "maximum": MAX_STAND_OFF_M,
                    },
                },
                "required": ["object_id", "stand_off_m"],
            },
        },
        {
            "name": "face_nearest_person",
            "description": "Turn in place to face the nearest person; do not approach them.",
            "behavior": blocking,
            "parameters": {"type": "OBJECT", "properties": {}},
        },
        {
            "name": "speak",
            "description": "Speak one short line through the robot's TTS adapter.",
            "behavior": blocking,
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "message": {
                        "type": "STRING",
                        "maxLength": MAX_SPEECH_CHARS,
                    }
                },
                "required": ["message"],
            },
        },
        {
            "name": "stop",
            "description": "Cancel the active mission and stop safely.",
            "behavior": blocking,
            "parameters": {
                "type": "OBJECT",
                "properties": {"reason": {"type": "STRING"}},
                "required": ["reason"],
            },
        },
    ]


def live_tools() -> list[dict[str, Any]]:
    return [{"function_declarations": function_declarations()}]
