#!/usr/bin/env python3
"""Relay browser teleop (Twist) onto the sim's /cmd_vel (TwistStamped).

Lichtblick's Teleop panel publishes geometry_msgs/Twist with no header — the
panel bundle has no TwistStamped path at all. turtlebot3_burger_cam_bridge.yaml
bridges /cmd_vel as geometry_msgs/msg/TwistStamped, and ros_gz drops a
mismatched type at the bridge WITHOUT logging anything, so wiring the panel
straight to /cmd_vel fails as "the panel works, the robot never moves". This
node is the adapter that makes the browser a usable teleop source.

The deadman is the part that matters. The Teleop panel publishes repeatedly
while a button is held and simply STOPS publishing when released — it never
sends a zero. Relaying naively means the last non-zero velocity latches and
the robot drives into a wall after the operator has let go. So a missing input
is treated as "stop": if no Twist arrives for DEADMAN_S, we publish zero once
and stay quiet until input resumes.

Zero is published once rather than continuously because the diff-drive plugin
holds the last command; repeating it every tick would just add bridge traffic
to a sim that is already software-rendering every frame.
"""
import rclpy
from geometry_msgs.msg import Twist, TwistStamped
from rclpy.node import Node

# Longer than the panel's publish period (it defaults well under 10 Hz) so
# normal gaps between messages never trip it, short enough that letting go of
# a key stops the robot within roughly its own body length at 0.3 m/s.
DEADMAN_S = 0.4


class TeleopRelay(Node):

    def __init__(self):
        super().__init__('teleop_relay')
        self.declare_parameter('frame_id', 'base_footprint')
        self.frame_id = self.get_parameter('frame_id').value

        self.pub = self.create_publisher(TwistStamped, 'cmd_vel', 10)
        self.sub = self.create_subscription(
            Twist, 'cmd_vel_teleop', self.on_twist, 10)

        self.last_rx = None
        self.stopped = True
        self.create_timer(DEADMAN_S / 2.0, self.check_deadman)
        self.get_logger().info(
            'relaying cmd_vel_teleop (Twist) -> cmd_vel (TwistStamped), '
            f'deadman {DEADMAN_S:.1f}s')

    def stamp(self, twist):
        msg = TwistStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.frame_id
        msg.twist = twist
        return msg

    def on_twist(self, msg: Twist):
        self.last_rx = self.get_clock().now()
        self.stopped = False
        self.pub.publish(self.stamp(msg))

    def check_deadman(self):
        if self.stopped or self.last_rx is None:
            return
        age = (self.get_clock().now() - self.last_rx).nanoseconds / 1e9
        if age >= DEADMAN_S:
            self.pub.publish(self.stamp(Twist()))  # all-zero == stop
            self.stopped = True


def main(argv=None):
    rclpy.init(args=argv)
    node = TeleopRelay()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
