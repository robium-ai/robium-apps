"""Shared constants and the action -> wheel mapping.

The action space is the game controller's own axes, so a recorded human
demonstration and a policy rollout are the same two numbers travelling the same
path to the wheels.
"""

from __future__ import annotations

import numpy as np

# Control rate for both teleoperation and policy rollouts.
CONTROL_HZ = 10.0


def mix(action: np.ndarray | tuple[float, float]) -> tuple[float, float]:
    """Map a normalized (throttle, steer) action to per-wheel fractions in [-1, 1].

    Rescales rather than clips when differential mixing overflows, so a
    hard-forward hard-turn command keeps its curvature instead of flattening
    into a straight line.
    """
    throttle = float(np.clip(action[0], -1.0, 1.0))
    steer = float(np.clip(action[1], -1.0, 1.0))

    left = throttle + steer
    right = throttle - steer

    peak = max(abs(left), abs(right))
    if peak > 1.0:
        left /= peak
        right /= peak
    return left, right
