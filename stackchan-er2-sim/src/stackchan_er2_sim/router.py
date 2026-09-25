"""Deterministic, zero-key command router for the first-run demo."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Command:
    action: str
    speech: str
    yaw: float = 0.0
    pitch: float = 45.0
    tracking: str | None = None


def route(text: str) -> Command:
    normalized = " ".join(text.casefold().strip().split())
    if not normalized:
        return Command("none", "I didn't catch that. Try saying look left or track me.")
    if any(phrase in normalized for phrase in ("stop tracking", "stop following", "don't track")):
        return Command("center", "Okay, I stopped tracking you.", tracking="stop")
    if any(phrase in normalized for phrase in ("track me", "follow me", "follow my face")):
        return Command("center", "I can follow you. Enable the camera if your browser asks.", tracking="start")
    if "look left" in normalized:
        return Command("move", "Looking left.", yaw=30)
    if "look right" in normalized:
        return Command("move", "Looking right.", yaw=-30)
    if any(phrase in normalized for phrase in ("look up", "look upward")):
        return Command("move", "Looking up.", pitch=70)
    if any(phrase in normalized for phrase in ("look down", "look downward")):
        return Command("move", "Looking down.", pitch=20)
    if any(phrase in normalized for phrase in ("look straight", "look forward", "center")):
        return Command("center", "Back to center.")
    if any(word in normalized for word in ("nod", "yes")):
        return Command("nod", "Yes!")
    if any(phrase in normalized for phrase in ("shake", "say no", "no no")):
        return Command("shake", "Nope.")
    if any(phrase in normalized for phrase in ("introduce yourself", "who are you")):
        return Command(
            "nod",
            "Hi! I'm Stack-chan in MuJoCo. My ears and voice are running locally on this computer.",
        )
    if any(phrase in normalized for phrase in ("show what you can do", "demo", "show me")):
        return Command(
            "showcase",
            "I can look around, nod, shake my head, speak locally, and track your face.",
        )
    return Command(
        "none",
        "For this local demo, try look left, nod, introduce yourself, or track me.",
    )
