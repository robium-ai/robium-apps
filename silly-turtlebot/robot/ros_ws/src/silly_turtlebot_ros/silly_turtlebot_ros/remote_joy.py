"""Receive watchdog-protected joystick snapshots from the robot's Orin."""

from __future__ import annotations

import json
import math
import socket
import time
from typing import Any

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Joy

MAGIC = "silly-turtlebot-joy-v1"


class RemoteJoy(Node):
    def __init__(self) -> None:
        super().__init__("remote_joy")
        self.declare_parameter("bind_host", "0.0.0.0")
        self.declare_parameter("port", 8766)
        self.declare_parameter("allowed_hosts", ["10.42.0.2", "192.168.0.51"])
        self.declare_parameter("timeout_s", 0.35)
        self.declare_parameter("joy_topic", "/joy")

        bind_host = str(self.get_parameter("bind_host").value)
        port = int(self.get_parameter("port").value)
        self.allowed_hosts = {
            str(host) for host in self.get_parameter("allowed_hosts").value
        }
        self.timeout_s = float(self.get_parameter("timeout_s").value)
        self.publisher = self.create_publisher(
            Joy, str(self.get_parameter("joy_topic").value), 10
        )
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setblocking(False)
        self.sock.bind((bind_host, port))
        self.last_packet_at = 0.0
        self.last_axes: list[float] = []
        self.last_buttons: list[int] = []
        self.stopped = True
        self.create_timer(0.01, self._poll)
        self.get_logger().info(
            f"remote gamepad ready on UDP {bind_host}:{port}; sources "
            f"{', '.join(sorted(self.allowed_hosts))}"
        )

    def _poll(self) -> None:
        while True:
            try:
                payload, address = self.sock.recvfrom(8192)
            except BlockingIOError:
                break
            if address[0] not in self.allowed_hosts:
                continue
            message = self._decode(payload)
            if message is None:
                continue
            self.last_axes = message["axes"]
            self.last_buttons = message["buttons"]
            self.last_packet_at = time.monotonic()
            self.stopped = False
            self._publish(self.last_axes, self.last_buttons)

        if not self.stopped and time.monotonic() - self.last_packet_at > self.timeout_s:
            self._publish(
                [0.0 for _ in self.last_axes], [0 for _ in self.last_buttons]
            )
            self.stopped = True
            self.get_logger().warning("remote gamepad timed out; published stop")

    @staticmethod
    def _decode(payload: bytes) -> dict[str, Any] | None:
        try:
            message = json.loads(payload)
            axes = [float(value) for value in message["axes"]]
            buttons = [1 if int(value) else 0 for value in message["buttons"]]
            if (
                message.get("magic") != MAGIC
                or not 2 <= len(axes) <= 32
                or not 6 <= len(buttons) <= 64
                or not all(math.isfinite(value) for value in axes)
            ):
                return None
            axes = [max(-1.0, min(1.0, value)) for value in axes]
            return {"axes": axes, "buttons": buttons}
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def _publish(self, axes: list[float], buttons: list[int]) -> None:
        message = Joy()
        message.header.stamp = self.get_clock().now().to_msg()
        message.header.frame_id = "stadia_orin"
        message.axes = axes
        message.buttons = buttons
        self.publisher.publish(message)

    def destroy_node(self) -> bool:
        self.sock.close()
        return super().destroy_node()


def main() -> None:
    rclpy.init()
    node = RemoteJoy()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
