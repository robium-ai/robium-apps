"""Map spare buttons from TurtleBot 4's always-on joystick to dock actions."""

from __future__ import annotations

from typing import Any

import rclpy
from irobot_create_msgs.action import Dock, Undock
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Joy


class GamepadActions(Node):
    """Fire dock/undock once per button press while drive buttons are released."""

    def __init__(self) -> None:
        super().__init__("gamepad_actions")
        self.declare_parameter("joy_topic", "/joy")
        self.declare_parameter("undock_button", 0)  # Stadia A
        self.declare_parameter("dock_button", 1)  # Stadia B
        self.declare_parameter("enable_button", 4)  # stock TB4 left shoulder
        self.declare_parameter("turbo_button", 5)  # stock TB4 right shoulder
        self.declare_parameter("dock_action", "/dock")
        self.declare_parameter("undock_action", "/undock")

        self.undock_button = int(self.get_parameter("undock_button").value)
        self.dock_button = int(self.get_parameter("dock_button").value)
        self.enable_button = int(self.get_parameter("enable_button").value)
        self.turbo_button = int(self.get_parameter("turbo_button").value)
        self._previous_buttons: list[int] = []
        self._active_goal: Any = None
        self._active_name = ""

        self._dock_client = ActionClient(
            self, Dock, str(self.get_parameter("dock_action").value)
        )
        self._undock_client = ActionClient(
            self, Undock, str(self.get_parameter("undock_action").value)
        )
        self._joy_subscription = self.create_subscription(
            Joy,
            str(self.get_parameter("joy_topic").value),
            self._on_joy,
            qos_profile_sensor_data,
        )
        self.get_logger().info(
            "gamepad ready: A/button %d undocks, B/button %d docks; "
            "stock shoulder-button drive remains unchanged"
            % (self.undock_button, self.dock_button)
        )

    @staticmethod
    def _pressed(buttons: list[int], index: int) -> bool:
        return 0 <= index < len(buttons) and bool(buttons[index])

    def _on_joy(self, message: Joy) -> None:
        buttons = list(message.buttons)
        drive_enabled = self._pressed(buttons, self.enable_button) or self._pressed(
            buttons, self.turbo_button
        )
        for index, name, client, goal in (
            (self.undock_button, "undock", self._undock_client, Undock.Goal()),
            (self.dock_button, "dock", self._dock_client, Dock.Goal()),
        ):
            pressed = self._pressed(buttons, index)
            was_pressed = self._pressed(self._previous_buttons, index)
            if pressed and not was_pressed:
                if drive_enabled:
                    self.get_logger().warning(
                        f"ignored {name}: release both drive shoulder buttons first"
                    )
                else:
                    self._fire(client, goal, name)
        self._previous_buttons = buttons

    def _fire(self, client: ActionClient, goal: Any, name: str) -> None:
        if self._active_goal is not None:
            self.get_logger().warning(
                f"ignored {name}: {self._active_name} is already active"
            )
            return
        if not client.server_is_ready():
            self.get_logger().error(f"{name} action server is unavailable")
            return
        self.get_logger().info(f"gamepad {name} requested")
        self._active_goal = "pending"
        self._active_name = name
        client.send_goal_async(goal).add_done_callback(
            lambda future, name=name: self._on_goal(future, name)
        )

    def _on_goal(self, future: Any, name: str) -> None:
        try:
            handle = future.result()
            if handle is None or not handle.accepted:
                self.get_logger().warning(f"gamepad {name} goal rejected")
                self._active_goal = None
                self._active_name = ""
                return
            self._active_goal = handle
            handle.get_result_async().add_done_callback(
                lambda result, name=name: self._on_result(result, name)
            )
        except Exception as exc:  # noqa: BLE001 - log rclpy callback failure.
            self.get_logger().error(f"gamepad {name} request failed: {exc}")
            self._active_goal = None
            self._active_name = ""

    def _on_result(self, future: Any, name: str) -> None:
        try:
            wrapped = future.result()
            status = getattr(wrapped, "status", "unknown")
            self.get_logger().info(f"gamepad {name} finished with status {status}")
        except Exception as exc:  # noqa: BLE001 - log rclpy callback failure.
            self.get_logger().error(f"gamepad {name} result failed: {exc}")
        finally:
            self._active_goal = None
            self._active_name = ""


def main() -> None:
    rclpy.init()
    node = GamepadActions()
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
