"""Shared constants, the action -> wheel mapping, and the chassis calibration.

Two mappings live here, and keeping them apart matters. `mix` turns a normalized
(throttle, steer) action into per-wheel fractions and is pure geometry - the same
function the simulated sibling app uses, so a demonstration recorded there and
one recorded here mean the same thing. `RobotConfig` turns wheel fractions into
the two motor numbers *this particular chassis* wants, and is pure wiring: which
motor is on the left, which way each one is soldered, and how much duty the
gearboxes need before they turn at all.

Only the second half is allowed to differ between robots, which is why it is the
only half written to disk.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

# Control rate for teleoperation, recording, and any later policy rollout.
# Faster than the simulated sibling: a real chassis with real latency is
# unpleasant to drive at 10 Hz, and the camera has frames to spare.
CONTROL_HZ = 20.0

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.json"

# The mBot's USB-serial bridge: a WCH CH340. macOS binds it with its built-in
# AppleUSBCHCOM driver, so nothing needs installing.
CH340_VID = 0x1A86


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


@dataclass
class RobotConfig:
    """Everything about this chassis that a different mBot might not share."""

    port: str | None = None

    # Control rate, and also the recorded dataset's fps. Raising it shortens
    # the gap between moving the stick and the wheels reacting, but only up to
    # the transport's own latency: over USB a command lands in well under a
    # millisecond, while over BLE it waits for the next connection interval,
    # which the measured 60 ms confirmed round trip puts at roughly 25-30 ms
    # each way. Asking for 50 Hz over Bluetooth therefore buys nothing but
    # duplicated frames.
    control_hz: float = 20.0
    # The wire rate, which must match whatever the board is talking at. Over USB
    # that is the firmware's own Serial.begin. Over Bluetooth it is the module's
    # configured rate, because the module and the ATmega talk to each other on
    # the same UART - the module is a pipe, not a translator, so a module set to
    # 9600 makes the whole link 9600 no matter what the sketch asks for.
    baud: int = 115200
    camera_index: int = 0
    # Preferred camera by name, e.g. "I930". Beats camera_index when set, and
    # should be: macOS renumbers cameras when a phone joins or leaves over
    # Continuity, so an index can quietly start pointing somewhere else.
    camera_name: str | None = None
    # Measured camera name -> OpenCV index, written by `./app cameras
    # --identify`. Needed because OpenCV's index order and AVFoundation's
    # device order genuinely differ, and neither API exposes the other's.
    camera_map: dict[str, int] | None = None
    camera_width: int = 640
    camera_height: int = 480

    # Duty cycle, 0-255. A geared DC motor does not turn at all below some
    # threshold, so a raw proportional map wastes the bottom half of the stick
    # on silence; min_pwm is where "barely moving" actually begins.
    min_pwm: int = 60
    max_pwm: int = 200

    # Which stick axes to read. Defaults suit an Xbox-style layout (left
    # stick vertical, right stick horizontal); controllers disagree, so
    # `./app gamepad` shows the live values and these can be changed.
    throttle_axis: int = 1
    steer_axis: int = 2

    # How much of the stick's steer travel to actually use. A differential
    # drive turns by driving its wheels in opposite directions, so full steer
    # is a spin-on-the-spot at full speed - far twitchier than is useful for
    # driving, and far twitchier than makes a good demonstration to clone.
    # Scaling here rather than in `mix` keeps the action space canonical: what
    # gets recorded is still the stick, and a policy replaying it goes through
    # this same scaling on the way to the wheels.
    steer_gain: float = 0.45

    # How much stick travel around centre counts as "centred". Sticks rarely
    # rest at exactly zero, and on a robot that drifts into a slow creep the
    # moment nobody is touching it - which also writes a nonzero action into
    # every idle frame of a recording.
    stick_deadzone: float = 0.12

    # Wiring, discovered by `./app calibrate` rather than assumed.
    swap_motors: bool = False
    invert_left: bool = False
    invert_right: bool = True

    # The board stops the wheels if it hears nothing for this long. It must
    # comfortably exceed one control period or normal driving trips it.
    watchdog_ms: int = 400

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> "RobotConfig":
        if path.exists():
            return cls(**json.loads(path.read_text()))
        return cls()

    def save(self, path: Path = CONFIG_PATH) -> None:
        path.write_text(json.dumps(asdict(self), indent=2) + "\n")

    def wheels(self, action: np.ndarray | tuple[float, float]) -> tuple[float, float]:
        """A normalized (throttle, steer) action -> per-wheel fractions."""
        return mix((action[0], action[1] * self.steer_gain))

    def to_pwm(self, left: float, right: float) -> tuple[int, int]:
        """Wheel fractions in [-1, 1] -> the two motor values the board wants."""
        if self.invert_left:
            left = -left
        if self.invert_right:
            right = -right

        m1, m2 = self._duty(left), self._duty(right)
        return (m2, m1) if self.swap_motors else (m1, m2)

    def _duty(self, fraction: float) -> int:
        fraction = float(np.clip(fraction, -1.0, 1.0))
        # A true zero has to stay a true zero: a stopped wheel must not creep.
        if abs(fraction) < 1e-3:
            return 0
        span = self.max_pwm - self.min_pwm
        magnitude = self.min_pwm + span * abs(fraction)
        return int(round(np.sign(fraction) * magnitude))
