#!/usr/bin/env python3
"""tb4-teleop robot-side helper.

Dock/undock on the Create 3 are ROS 2 *actions*, which a Foxglove button can't
call directly. This node bridges them to two trivial topic triggers so a
Foxglove "Publish" panel acts as DOCK / UNDOCK buttons:

    publish std_msgs/Empty to  /teleop/dock    -> fires the /dock   action
    publish std_msgs/Empty to  /teleop/undock  -> fires the /undock action

Runs on the robot alongside foxglove_bridge (deployed + launched by
scripts/start_bridge.sh). Must be started in the turtlebot4 environment so it
discovers the Create 3 base's action servers.
"""
import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from std_msgs.msg import Empty

from irobot_create_msgs.action import Dock, Undock


class TeleopActions(Node):
    def __init__(self):
        super().__init__('tb4_teleop_actions')
        self._dock_client = ActionClient(self, Dock, 'dock')
        self._undock_client = ActionClient(self, Undock, 'undock')
        self.create_subscription(Empty, 'teleop/dock', self._on_dock, 1)
        self.create_subscription(Empty, 'teleop/undock', self._on_undock, 1)
        self.get_logger().info('tb4_teleop_actions ready: /teleop/dock /teleop/undock')

    def _fire(self, client, goal, name):
        self.get_logger().info(f'{name} requested')
        if not client.wait_for_server(timeout_sec=3.0):
            self.get_logger().error(f'{name} action server unavailable')
            return
        client.send_goal_async(goal)

    def _on_dock(self, _msg):
        self._fire(self._dock_client, Dock.Goal(), 'dock')

    def _on_undock(self, _msg):
        self._fire(self._undock_client, Undock.Goal(), 'undock')


def main():
    rclpy.init()
    node = TeleopActions()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
