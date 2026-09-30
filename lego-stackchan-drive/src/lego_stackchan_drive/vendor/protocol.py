"""Small, fixed-width protocol shared conceptually by the host and hub.

The hub input is a byte stream. Each drive packet begins with ``D`` and carries
two power bytes biased by 100, so no text parsing or packet-length negotiation
sits in the control path. PING and EXIT are single-byte control messages.
"""

from __future__ import annotations

DRIVE = b"D"
PING = b"P"
EXIT = b"X"

READY_LINE = "READY"
PONG_LINE = "PONG"

MIN_POWER = -100
MAX_POWER = 100
POWER_BIAS = 100


def encode_drive(left: int, right: int) -> bytes:
    """Encode signed motor powers, rejecting unsafe/out-of-contract values."""
    values = (left, right)
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        raise TypeError("motor powers must be integers")
    if any(value < MIN_POWER or value > MAX_POWER for value in values):
        raise ValueError("motor power must be between -100 and 100")
    return DRIVE + bytes((left + POWER_BIAS, right + POWER_BIAS))


def decode_drive(packet: bytes) -> tuple[int, int]:
    """Decode a drive packet. Used by tests and protocol diagnostics."""
    if len(packet) != 3 or packet[:1] != DRIVE:
        raise ValueError("not a three-byte drive packet")
    return packet[1] - POWER_BIAS, packet[2] - POWER_BIAS


def mix(throttle: float, steer: float, speed: int) -> tuple[int, int]:
    """Mix normalized throttle/steer into curvature-preserving wheel powers.

    Positive steer means right. If throttle and steer would overflow, both
    wheels are scaled together instead of independently clipped, preserving the
    requested curve.
    """
    if not MIN_POWER <= speed <= MAX_POWER:
        raise ValueError("speed must be between -100 and 100")
    throttle = max(-1.0, min(1.0, float(throttle)))
    steer = max(-1.0, min(1.0, float(steer)))
    left = throttle + steer
    right = throttle - steer
    scale = max(1.0, abs(left), abs(right))
    return round(left / scale * speed), round(right / scale * speed)


class LineDecoder:
    """Reassemble newline-delimited stdout split across BLE notifications."""

    def __init__(self) -> None:
        self._partial = bytearray()

    def feed(self, payload: bytes) -> list[str]:
        self._partial.extend(payload)
        lines: list[str] = []
        while b"\n" in self._partial:
            raw, _, rest = self._partial.partition(b"\n")
            self._partial = bytearray(rest)
            line = raw.decode("ascii", "replace").strip()
            if line:
                lines.append(line)
        return lines
