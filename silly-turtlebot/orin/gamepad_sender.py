"""Forward a Linux joystick from the Orin to the TurtleBot ROS bridge."""

from __future__ import annotations

import json
import math
import os
import select
import socket
import struct
import time

DEVICE = os.environ.get("GAMEPAD_DEVICE", "/dev/input/js0")
ROBOT_HOSTS = [
    host.strip()
    for host in os.environ.get(
        "GAMEPAD_ROBOT_HOSTS",
        os.environ.get("GAMEPAD_ROBOT_HOST", "192.168.0.50"),
    ).split(",")
    if host.strip()
]
ROBOT_PORT = int(os.environ.get("GAMEPAD_ROBOT_PORT", "8766"))
SEND_HZ = float(os.environ.get("GAMEPAD_SEND_HZ", "20"))
DEADZONE = float(os.environ.get("GAMEPAD_DEADZONE", "0.08"))
INVERT_AXES = {
    int(value)
    for value in os.environ.get("GAMEPAD_INVERT_AXES", "0,1").split(",")
    if value.strip()
}
MAGIC = "silly-turtlebot-joy-v1"

EVENT = struct.Struct("IhBB")
BUTTON = 0x01
AXIS = 0x02
INITIAL = 0x80


def _shape_axis(value: float) -> float:
    """Remove center noise, then preserve proportional travel to full scale."""
    magnitude = abs(value)
    if magnitude <= DEADZONE:
        return 0.0
    return math.copysign((magnitude - DEADZONE) / (1.0 - DEADZONE), value)


def _set(values: list[float | int], index: int, value: float | int) -> None:
    if index >= len(values):
        values.extend([0] * (index + 1 - len(values)))
    values[index] = value


def main() -> None:
    destinations = [(host, ROBOT_PORT) for host in ROBOT_HOSTS]
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sequence = 0
    targets = ", ".join(f"{host}:{port}" for host, port in destinations)
    print(f"gamepad forwarder ready: {DEVICE} -> {targets}", flush=True)

    while True:
        try:
            descriptor = os.open(DEVICE, os.O_RDONLY | os.O_NONBLOCK)
        except OSError:
            time.sleep(1)
            continue

        axes: list[float | int] = []
        buttons: list[float | int] = []
        print(f"gamepad connected: {DEVICE}", flush=True)
        try:
            next_send = time.monotonic()
            while True:
                readable, _, _ = select.select([descriptor], [], [], 0.01)
                if readable:
                    data = os.read(descriptor, EVENT.size * 64)
                    if not data:
                        raise OSError("gamepad disconnected")
                    for offset in range(0, len(data) - EVENT.size + 1, EVENT.size):
                        _, value, event_type, number = EVENT.unpack_from(data, offset)
                        event_type &= ~INITIAL
                        if event_type == AXIS:
                            normalized = max(-1.0, min(1.0, value / 32767.0))
                            normalized = _shape_axis(normalized)
                            _set(axes, number, -normalized if number in INVERT_AXES else normalized)
                        elif event_type == BUTTON:
                            _set(buttons, number, 1 if value else 0)

                now = time.monotonic()
                if axes and buttons and now >= next_send:
                    sequence += 1
                    packet = {
                        "magic": MAGIC,
                        "sequence": sequence,
                        "axes": axes,
                        "buttons": buttons,
                    }
                    payload = json.dumps(packet, separators=(",", ":")).encode()
                    for destination in destinations:
                        try:
                            sock.sendto(payload, destination)
                        except OSError:
                            # One path may be down; the other remains a live fallback.
                            pass
                    next_send = now + (1.0 / SEND_HZ)
        except OSError as exc:
            print(f"gamepad unavailable: {exc}; waiting for reconnect", flush=True)
        finally:
            os.close(descriptor)


if __name__ == "__main__":
    main()
