"""Loopback HTTP bridge owning Nav2 actions and compressed camera topics."""

from __future__ import annotations

import json
import math
import shlex
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import rclpy
import yaml
from action_msgs.msg import GoalStatus
from action_msgs.srv import CancelGoal
from geometry_msgs.msg import PoseStamped
from irobot_create_msgs.action import Dock, Undock
from irobot_create_msgs.msg import DockStatus
from nav2_msgs.action import DriveOnHeading, NavigateToPose, Spin
from rclpy.action import ActionClient
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CompressedImage


class SillyTurtleBotBridge(Node):
    def __init__(self) -> None:
        super().__init__("silly_turtlebot_bridge")
        self.declare_parameter("waypoints_file", "")
        self.declare_parameter("bind_host", "127.0.0.1")
        self.declare_parameter("port", 8088)
        self.declare_parameter("navigate_action", "/navigate_to_pose")
        self.declare_parameter("drive_on_heading_action", "/drive_on_heading")
        self.declare_parameter("spin_action", "/spin")
        self.declare_parameter("dock_action", "/dock")
        self.declare_parameter("undock_action", "/undock")
        self.declare_parameter(
            "primary_camera_topic", "/oakd/rgb/preview/image_raw/compressed"
        )
        self.declare_parameter("secondary_camera_topic", "")
        self.declare_parameter("camera_stale_s", 3.0)
        self.declare_parameter("navigate_timeout_s", 180.0)
        self.declare_parameter("drive_timeout_s", 45.0)
        self.declare_parameter("forward_speed_mps", 0.12)
        self.declare_parameter("spin_timeout_s", 45.0)
        self.declare_parameter("dock_timeout_s", 180.0)
        self.declare_parameter("undock_timeout_s", 60.0)
        self.declare_parameter("tts_command", "espeak-ng")

        self.bind_host = str(self.get_parameter("bind_host").value)
        self.port = int(self.get_parameter("port").value)
        self.camera_stale_s = float(self.get_parameter("camera_stale_s").value)
        self.navigate_timeout_s = float(self.get_parameter("navigate_timeout_s").value)
        self.drive_timeout_s = float(self.get_parameter("drive_timeout_s").value)
        self.forward_speed_mps = float(self.get_parameter("forward_speed_mps").value)
        self.spin_timeout_s = float(self.get_parameter("spin_timeout_s").value)
        self.dock_timeout_s = float(self.get_parameter("dock_timeout_s").value)
        self.undock_timeout_s = float(self.get_parameter("undock_timeout_s").value)
        self.tts_command = str(self.get_parameter("tts_command").value).strip()

        self.frame_id, self.waypoints = self._load_waypoints(
            Path(str(self.get_parameter("waypoints_file").value))
        )
        navigate_action = str(self.get_parameter("navigate_action").value)
        drive_action = str(self.get_parameter("drive_on_heading_action").value)
        spin_action = str(self.get_parameter("spin_action").value)
        dock_action = str(self.get_parameter("dock_action").value)
        undock_action = str(self.get_parameter("undock_action").value)
        self.navigate_client = ActionClient(
            self,
            NavigateToPose,
            navigate_action,
        )
        self.drive_client = ActionClient(
            self,
            DriveOnHeading,
            drive_action,
        )
        self.spin_client = ActionClient(self, Spin, spin_action)
        self.dock_client = ActionClient(self, Dock, dock_action)
        self.undock_client = ActionClient(self, Undock, undock_action)
        # ActionClient can cancel only goals it created. Lichtblick publishes
        # PoseStamped goals directly, so operator stop also calls Nav2's
        # server-side cancellation service to cover those external goals.
        self._navigate_cancel_client = self.create_client(
            CancelGoal, f"{navigate_action}/_action/cancel_goal"
        )

        self._motion_lock = threading.Lock()
        self._active_lock = threading.Lock()
        self._active_goal = None
        self._dock_status_lock = threading.Lock()
        self._is_docked: bool | None = None
        self._dock_status_subscription = self.create_subscription(
            DockStatus,
            "/dock_status",
            self._on_dock_status,
            qos_profile_sensor_data,
        )
        self._camera_lock = threading.Lock()
        self._cameras: dict[str, tuple[bytes, float]] = {}
        self.camera_topics = {
            "primary": str(self.get_parameter("primary_camera_topic").value),
            "secondary": str(self.get_parameter("secondary_camera_topic").value),
        }
        self._camera_subscriptions = []
        for source, topic in self.camera_topics.items():
            if topic:
                subscription = self.create_subscription(
                    CompressedImage,
                    topic,
                    lambda message, source=source: self._on_camera(source, message),
                    qos_profile_sensor_data,
                )
                self._camera_subscriptions.append(subscription)

        self.get_logger().info(
            f"bridge ready on http://{self.bind_host}:{self.port}; "
            f"locations={sorted(self.waypoints)}"
        )

    @staticmethod
    def _load_waypoints(path: Path) -> tuple[str, dict[str, dict[str, float]]]:
        if not path.is_file():
            raise RuntimeError(f"waypoints file does not exist: {path}")
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        frame_id = str(raw.get("frame_id", "odom"))
        waypoints: dict[str, dict[str, float]] = {}
        for name, values in (raw.get("locations") or {}).items():
            if not isinstance(values, dict) or values.get("configured") is not True:
                continue
            pose = {field: float(values[field]) for field in ("x", "y", "yaw")}
            if not all(math.isfinite(value) for value in pose.values()):
                raise RuntimeError(f"waypoint {name!r} has a non-finite pose")
            waypoints[str(name)] = pose
        return frame_id, waypoints

    def _on_camera(self, source: str, message: CompressedImage) -> None:
        image = bytes(message.data)
        if not image:
            return
        with self._camera_lock:
            self._cameras[source] = (image, time.monotonic())

    def _on_dock_status(self, message: DockStatus) -> None:
        with self._dock_status_lock:
            self._is_docked = bool(message.is_docked)

    def camera(self, source: str) -> bytes | None:
        with self._camera_lock:
            item = self._cameras.get(source)
        if item is None or time.monotonic() - item[1] > self.camera_stale_s:
            return None
        return item[0]

    def health(self) -> dict[str, Any]:
        now = time.monotonic()
        navigate_ready = self.navigate_client.server_is_ready()
        drive_ready = self.drive_client.server_is_ready()
        spin_ready = self.spin_client.server_is_ready()
        dock_ready = self.dock_client.server_is_ready()
        undock_ready = self.undock_client.server_is_ready()
        with self._dock_status_lock:
            is_docked = self._is_docked
        cameras = {}
        with self._camera_lock:
            snapshots = dict(self._cameras)
        for source, topic in self.camera_topics.items():
            item = snapshots.get(source)
            age_s = None if item is None else round(now - item[1], 3)
            cameras[source] = {
                "topic": topic,
                "fresh": age_s is not None and age_s <= self.camera_stale_s,
                "age_s": age_s,
            }
        return {
            "status": (
                "ok"
                if navigate_ready
                and drive_ready
                and spin_ready
                and dock_ready
                and undock_ready
                else "starting"
            ),
            "navigate_to_pose": navigate_ready,
            "drive_on_heading": drive_ready,
            "spin": spin_ready,
            "dock": dock_ready,
            "undock": undock_ready,
            "is_docked": is_docked,
            "locations": sorted(self.waypoints),
            "cameras": cameras,
        }

    def navigate(self, location: str) -> dict[str, Any]:
        waypoint = self.waypoints.get(location)
        if waypoint is None:
            return {
                "status": "rejected",
                "reason": f"location is not configured for this run: {location}",
            }
        goal = NavigateToPose.Goal()
        pose = PoseStamped()
        pose.header.frame_id = self.frame_id
        pose.header.stamp = self.get_clock().now().to_msg()
        pose.pose.position.x = waypoint["x"]
        pose.pose.position.y = waypoint["y"]
        pose.pose.orientation.z = math.sin(waypoint["yaw"] / 2.0)
        pose.pose.orientation.w = math.cos(waypoint["yaw"] / 2.0)
        goal.pose = pose
        result = self._run_action(
            self.navigate_client, goal, self.navigate_timeout_s, "navigate_to_pose"
        )
        result["location"] = location
        return result

    def look_around(self, quarter_turns: int) -> dict[str, Any]:
        if isinstance(quarter_turns, bool) or not 1 <= quarter_turns <= 4:
            return {"status": "rejected", "reason": "quarter_turns must be 1..4"}
        completed = 0
        for _ in range(quarter_turns):
            goal = Spin.Goal()
            goal.target_yaw = math.pi / 2.0
            goal.time_allowance.sec = int(self.spin_timeout_s)
            result = self._run_action(
                self.spin_client, goal, self.spin_timeout_s + 5.0, "spin"
            )
            if result.get("status") != "succeeded":
                result["quarter_turns"] = quarter_turns
                result["completed_quarter_turns"] = completed
                result["visible_objects"] = []
                return result
            completed += 1
        return {
            "status": "succeeded",
            "quarter_turns": quarter_turns,
            "completed_quarter_turns": completed,
            "visible_objects": [],
        }

    def move_forward(self, distance_m: Any) -> dict[str, Any]:
        if isinstance(distance_m, bool) or not isinstance(distance_m, (int, float)):
            return {"status": "rejected", "reason": "distance_m must be numeric"}
        distance_m = float(distance_m)
        if not math.isfinite(distance_m) or not 0.1 <= distance_m <= 1.0:
            return {
                "status": "rejected",
                "reason": "distance_m must be between 0.1 and 1.0",
            }
        goal = DriveOnHeading.Goal()
        goal.target.x = distance_m
        goal.speed = self.forward_speed_mps
        goal.time_allowance.sec = int(self.drive_timeout_s)
        result = self._run_action(
            self.drive_client,
            goal,
            self.drive_timeout_s + 5.0,
            "drive_on_heading",
        )
        result["distance_m"] = distance_m
        return result

    def dock(self) -> dict[str, Any]:
        return self._run_action(
            self.dock_client, Dock.Goal(), self.dock_timeout_s, "dock"
        )

    def undock(self) -> dict[str, Any]:
        return self._run_action(
            self.undock_client, Undock.Goal(), self.undock_timeout_s, "undock"
        )

    def _run_action(self, client, goal, timeout_s: float, name: str) -> dict[str, Any]:
        if not self._motion_lock.acquire(blocking=False):
            return {"status": "rejected", "reason": "another motion is active"}
        try:
            if not client.wait_for_server(timeout_sec=3.0):
                return {"status": "failed", "reason": f"{name} server unavailable"}

            done = threading.Event()
            outcome: dict[str, Any] = {}

            def on_result(future) -> None:
                try:
                    wrapped = future.result()
                    outcome["status_code"] = int(wrapped.status)
                    outcome["status"] = (
                        "succeeded"
                        if wrapped.status == GoalStatus.STATUS_SUCCEEDED
                        else "failed"
                    )
                    if outcome["status"] == "failed":
                        outcome["reason"] = f"{name} ended with status {wrapped.status}"
                except Exception as exc:  # noqa: BLE001 - surface rclpy callback failures.
                    outcome.update(
                        status="failed", reason=f"{name} result error: {exc}"
                    )
                finally:
                    with self._active_lock:
                        self._active_goal = None
                    done.set()

            def on_goal(future) -> None:
                try:
                    handle = future.result()
                    if handle is None or not handle.accepted:
                        outcome.update(
                            status="rejected", reason=f"{name} goal rejected"
                        )
                        done.set()
                        return
                    with self._active_lock:
                        self._active_goal = handle
                    handle.get_result_async().add_done_callback(on_result)
                except Exception as exc:  # noqa: BLE001 - surface rclpy callback failures.
                    outcome.update(status="failed", reason=f"{name} goal error: {exc}")
                    done.set()

            client.send_goal_async(goal).add_done_callback(on_goal)
            if not done.wait(timeout_s):
                self.stop("action timeout")
                return {"status": "failed", "reason": f"{name} timed out"}
            return outcome
        finally:
            self._motion_lock.release()

    def stop(self, reason: Any) -> dict[str, Any]:
        if not isinstance(reason, str) or not reason.strip():
            return {"status": "rejected", "reason": "stop reason must be non-empty"}
        reason = reason.strip()[:240]
        pending = []
        # Cancel every NavigateToPose goal, including one published directly
        # by Lichtblick rather than created by this bridge.
        client = self._navigate_cancel_client
        if client.service_is_ready() or client.wait_for_service(timeout_sec=0.5):
            pending.append(client.call_async(CancelGoal.Request()))
        # Non-navigation motions are always created by this bridge, so their
        # goal handle is sufficient and avoids waiting on four idle services.
        with self._active_lock:
            handle = self._active_goal
        if handle is not None:
            pending.append(handle.cancel_goal_async())

        deadline = time.monotonic() + 5.0
        while pending and time.monotonic() < deadline:
            if all(future.done() for future in pending):
                break
            time.sleep(0.02)
        if any(not future.done() for future in pending):
            return {"status": "failed", "reason": "goal cancellation timed out"}

        canceled_goals = 0
        for future in pending:
            try:
                response = future.result()
                canceled_goals += len(response.goals_canceling) if response else 0
            except Exception as exc:  # noqa: BLE001 - report cancellation failures.
                self.get_logger().warning(f"action cancellation failed: {exc}")
        return {
            "status": "succeeded",
            "reason": reason,
            "active_goal": canceled_goals > 0,
            "canceled_goals": canceled_goals,
        }

    def speak(self, message: Any) -> dict[str, Any]:
        if not isinstance(message, str) or not message.strip():
            return {"status": "rejected", "reason": "speech must be non-empty"}
        message = message.strip()
        if len(message) > 240:
            return {"status": "rejected", "reason": "speech exceeds 240 characters"}
        command = shlex.split(self.tts_command)
        if not command:
            return {"status": "failed", "reason": "TTS command is not configured"}
        try:
            completed = subprocess.run(
                [*command, message],
                check=False,
                capture_output=True,
                text=True,
                timeout=20.0,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return {"status": "failed", "reason": f"TTS unavailable: {exc}"}
        if completed.returncode:
            return {
                "status": "failed",
                "reason": completed.stderr.strip() or "TTS command failed",
            }
        return {"status": "succeeded", "message": message}


class BridgeServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, bridge: SillyTurtleBotBridge):
        self.bridge = bridge
        super().__init__(address, BridgeHandler)


class BridgeHandler(BaseHTTPRequestHandler):
    server: BridgeServer

    def _json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 16_384:
            raise ValueError("request is too large")
        return json.loads(self.rfile.read(length) or b"{}")

    def _write_json(self, payload: dict[str, Any], status: int = 200) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path == "/v1/health":
            self._write_json(self.server.bridge.health())
            return
        if self.path.startswith("/v1/camera/"):
            source = self.path.removeprefix("/v1/camera/")
            if source not in {"primary", "secondary"}:
                self._write_json(
                    {"status": "rejected", "reason": "unknown camera"}, 404
                )
                return
            frame = self.server.bridge.camera(source)
            if frame is None:
                self._write_json({"status": "failed", "reason": "no fresh frame"}, 503)
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(frame)))
            self.end_headers()
            self.wfile.write(frame)
            return
        self._write_json({"status": "rejected", "reason": "unknown endpoint"}, 404)

    def do_POST(self) -> None:
        try:
            payload = self._json_body()
            bridge = self.server.bridge
            if self.path == "/v1/navigate":
                result = bridge.navigate(str(payload.get("location", "")))
            elif self.path == "/v1/move-forward":
                result = bridge.move_forward(payload.get("distance_m"))
            elif self.path == "/v1/look-around":
                result = bridge.look_around(payload.get("quarter_turns"))
            elif self.path == "/v1/dock":
                result = bridge.dock()
            elif self.path == "/v1/undock":
                result = bridge.undock()
            elif self.path == "/v1/stop":
                result = bridge.stop(payload.get("reason", "operator request"))
            elif self.path == "/v1/speak":
                result = bridge.speak(payload.get("message"))
            elif self.path in {"/v1/approach-object", "/v1/face-nearest-person"}:
                result = {
                    "status": "rejected",
                    "reason": "depth/person grounding is not connected yet",
                }
            else:
                self._write_json(
                    {"status": "rejected", "reason": "unknown endpoint"}, 404
                )
                return
            self._write_json(result)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._write_json({"status": "rejected", "reason": str(exc)}, 400)

    def log_message(self, _format: str, *_args) -> None:
        return


def main() -> None:
    rclpy.init()
    node = SillyTurtleBotBridge()
    server = BridgeServer((node.bind_host, node.port), node)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
