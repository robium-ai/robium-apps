"""Relay an external HTTP JPEG camera into the local ROS 2 graph."""

from __future__ import annotations

import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)
from sensor_msgs.msg import CompressedImage


class ExternalCameraRelay(Node):
    def __init__(self) -> None:
        super().__init__("external_camera_relay")
        self.declare_parameter(
            "camera_url", "http://192.168.0.51:8081/preview.jpg"
        )
        self.declare_parameter(
            "topic", "/orin/oakd/preview/image_raw/compressed"
        )
        self.declare_parameter("frame_id", "oakd_rgb_camera_optical_frame")
        self.declare_parameter("publish_fps", 1.0)
        self.declare_parameter("request_timeout_s", 2.0)

        self.camera_url = str(self.get_parameter("camera_url").value)
        topic = str(self.get_parameter("topic").value)
        self.frame_id = str(self.get_parameter("frame_id").value)
        publish_fps = float(self.get_parameter("publish_fps").value)
        self.request_timeout_s = float(
            self.get_parameter("request_timeout_s").value
        )
        if not self.camera_url.startswith(("http://", "https://")):
            raise ValueError("camera_url must use http:// or https://")
        if not 0.1 <= publish_fps <= 12.0:
            raise ValueError("publish_fps must be between 0.1 and 12.0")
        if not 0.1 <= self.request_timeout_s <= 10.0:
            raise ValueError("request_timeout_s must be between 0.1 and 10.0")

        bridge_compatible_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )
        self.publisher = self.create_publisher(
            CompressedImage, topic, bridge_compatible_qos
        )
        self.last_warning_at = 0.0
        self.create_timer(1.0 / publish_fps, self._publish_frame)
        self.get_logger().info(
            f"relaying {self.camera_url} to {topic} at {publish_fps:.1f} FPS"
        )

    def _publish_frame(self) -> None:
        request = Request(self.camera_url, headers={"Accept": "image/jpeg"})
        try:
            with urlopen(request, timeout=self.request_timeout_s) as response:
                frame = response.read()
            if not frame:
                raise ValueError("camera returned an empty frame")
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            now = time.monotonic()
            if now - self.last_warning_at >= 10.0:
                self.get_logger().warning(f"camera frame unavailable: {exc}")
                self.last_warning_at = now
            return

        message = CompressedImage()
        message.header.stamp = self.get_clock().now().to_msg()
        message.header.frame_id = self.frame_id
        message.format = "jpeg"
        message.data = frame
        self.publisher.publish(message)


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = ExternalCameraRelay()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
