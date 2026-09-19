"""Make the console's Teleop panel drive the simulated robot, and stop it.

Two things stand between the bundled Lichtblick Teleop panel and the simulated
base, and neither reports an error -- the robot simply never moves:

1. **Message type.** The panel publishes `geometry_msgs/Twist`, which is what
   the physical robot's ROS 2 Humble stack subscribes to on `/cmd_vel`. The
   simulator runs Jazzy, where the same topic carries
   `geometry_msgs/TwistStamped`. ROS 2 lets both types coexist under one topic
   name, so the panel publishes happily into a topic nothing is listening to on
   that type. Converting here rather than forking the layout keeps one console
   working against both environments.

2. **Command latch.** Gazebo's DiffDrive system holds the last velocity it was
   handed indefinitely; there is no command timeout. The panel publishes only
   while a button is held and sends nothing on release, so the moment manual
   driving starts working the robot drives away and never stops. Real hardware
   provides that watchdog itself; the simulator does not.

**Why this runs as two processes.** A single node may not subscribe to `Twist`
and publish `TwistStamped` on one topic name: rmw rejects whichever endpoint is
created second as an incompatible type on an existing topic, in either order.
Separate processes each keep their own view, which is exactly how the panel and
the robot already coexist on `/cmd_vel` today. So the conversion is split:

    capture:  Twist        /cmd_vel        ->  TwistStamped  /cmd_vel_manual
    inject:   TwistStamped /cmd_vel_manual ->  TwistStamped  /cmd_vel

`inject` also owns the idle stop, because it is the stage that publishes to the
robot. It emits one stop per burst rather than a continuous stream, so it never
competes with Nav2 for the topic: Nav2's own commands never reach
`/cmd_vel_manual`, so nothing here reacts while Nav2 is driving.
"""

from __future__ import annotations

import rclpy
from geometry_msgs.msg import Twist, TwistStamped
from rclpy.node import Node

CAPTURE = "capture"
INJECT = "inject"


class TeleopRelay(Node):
    def __init__(self) -> None:
        super().__init__("teleop_relay")
        self.declare_parameter("mode", CAPTURE)
        self.declare_parameter("panel_topic", "/cmd_vel")
        self.declare_parameter("manual_topic", "/cmd_vel_manual")
        self.declare_parameter("robot_topic", "/cmd_vel")
        self.declare_parameter("frame_id", "base_link")
        # The panel is configured for 0.15 m/s and 0.4 rad/s. These bounds are
        # a backstop against a hand-edited layout, not the primary limit, and
        # they match the ceiling the semantic bridge allows Gemini to request.
        self.declare_parameter("max_linear_mps", 0.2)
        self.declare_parameter("max_angular_rps", 1.0)
        # Long enough not to trip between messages from the panel's 5 Hz
        # stream, short enough that a released button stops the robot promptly.
        self.declare_parameter("idle_stop_s", 0.6)

        self.mode = str(self.get_parameter("mode").value)
        if self.mode not in (CAPTURE, INJECT):
            raise ValueError(f"mode must be {CAPTURE!r} or {INJECT!r}")
        self.frame_id = str(self.get_parameter("frame_id").value)
        self.max_linear = abs(float(self.get_parameter("max_linear_mps").value))
        self.max_angular = abs(float(self.get_parameter("max_angular_rps").value))
        self.idle_stop_s = float(self.get_parameter("idle_stop_s").value)

        manual_topic = str(self.get_parameter("manual_topic").value)
        if self.mode == CAPTURE:
            self.publisher = self.create_publisher(TwistStamped, manual_topic, 10)
            self.create_subscription(
                Twist,
                str(self.get_parameter("panel_topic").value),
                self.on_panel,
                10,
            )
        else:
            self.publisher = self.create_publisher(
                TwistStamped, str(self.get_parameter("robot_topic").value), 10
            )
            self.create_subscription(
                TwistStamped, manual_topic, self.on_manual, 10
            )
            self.last_command_at: float | None = None
            self.moving = False
            self.create_timer(0.1, self.on_timer)

    def _now_s(self) -> float:
        return self.get_clock().now().nanoseconds / 1e9

    @staticmethod
    def _clamp(value: float, limit: float) -> float:
        return max(-limit, min(limit, value))

    def _publish(self, linear: float, angular: float) -> None:
        stamped = TwistStamped()
        stamped.header.stamp = self.get_clock().now().to_msg()
        stamped.header.frame_id = self.frame_id
        stamped.twist.linear.x = linear
        stamped.twist.angular.z = angular
        self.publisher.publish(stamped)

    def on_panel(self, message: Twist) -> None:
        self._publish(
            self._clamp(message.linear.x, self.max_linear),
            self._clamp(message.angular.z, self.max_angular),
        )

    def on_manual(self, message: TwistStamped) -> None:
        self.last_command_at = self._now_s()
        linear = message.twist.linear.x
        angular = message.twist.angular.z
        self.moving = linear != 0.0 or angular != 0.0
        self._publish(linear, angular)

    def on_timer(self) -> None:
        if not self.moving or self.last_command_at is None:
            return
        if self._now_s() - self.last_command_at < self.idle_stop_s:
            return
        # The panel went quiet with the robot still commanded to move: the
        # button was released. Send one stop, then stay silent so Nav2 keeps
        # sole ownership of the topic in between manual bursts.
        self.moving = False
        self._publish(0.0, 0.0)


def main() -> None:
    rclpy.init()
    node = TeleopRelay()
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
