"""Map browser-local face coordinates into bounded Stack-chan joints."""

from __future__ import annotations


def face_to_pose(x: float, y: float) -> tuple[float, float]:
    """Return yaw/pitch degrees for normalized image coordinates."""
    x = max(0.0, min(1.0, float(x)))
    y = max(0.0, min(1.0, float(y)))
    yaw = (0.5 - x) * 80.0
    pitch = 45.0 + (0.5 - y) * 70.0
    return max(-40.0, min(40.0, yaw)), max(10.0, min(80.0, pitch))
