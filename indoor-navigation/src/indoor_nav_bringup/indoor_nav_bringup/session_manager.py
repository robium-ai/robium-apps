#!/usr/bin/env python3
"""ROS services that manage the dashboard's simulator and map sessions."""

import math
import os
import signal
import subprocess
import threading

import rclpy
from geometry_msgs.msg import PoseStamped
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from rclpy.time import Time
from slam_toolbox.srv import SaveMap
from std_msgs.msg import String
from std_srvs.srv import Trigger
from tf2_ros import Buffer, TransformException, TransformListener

from .session_processes import SessionProcesses
from .waypoints import Waypoint, WaypointController, WaypointStore


LATCHED = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
SERVICE_TIMEOUT_S = 30.0


class ManagedProcess:
    """A ros2 launch process group with bounded, escalating shutdown."""

    def __init__(self, command):
        self.command = command
        self.process = subprocess.Popen(command, start_new_session=True)

    def stop(self):
        if self.process.poll() is not None:
            return
        group = os.getpgid(self.process.pid)
        os.killpg(group, signal.SIGINT)
        try:
            self.process.wait(timeout=10)
            return
        except subprocess.TimeoutExpired:
            os.killpg(group, signal.SIGTERM)
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(group, signal.SIGKILL)
            self.process.wait(timeout=5)


class SessionManager(Node):

    def __init__(self):
        super().__init__('session_manager')
        self.declare_parameter('map_name', 'map')
        self.declare_parameter('world', 'furnished_house')
        self.declare_parameter('maps_root', '/ws/maps')
        self.declare_parameter('waypoint_name', 'waypoint')
        self._lock = threading.RLock()
        group = ReentrantCallbackGroup()

        self._state_pub = self.create_publisher(String, '/mapping/state', LATCHED)
        self._maps_pub = self.create_publisher(String, '/maps/available', LATCHED)
        self._simulation_pub = self.create_publisher(
            String, '/simulation/state', LATCHED)
        self._waypoint_pub = self.create_publisher(
            String, '/waypoints/available', LATCHED)
        self._goal_pub = self.create_publisher(PoseStamped, '/goal_pose', 10)
        self._tf_buffer = Buffer()
        self._tf_listener = TransformListener(self._tf_buffer, self)
        self._save_client = self.create_client(
            SaveMap, '/slam_toolbox/save_map', callback_group=group)

        self._sessions = SessionProcesses(
            lambda role, command: self._start_child(role, command),
            self.get_parameter('maps_root').value,
            self.get_parameter('world').value,
        )
        self._waypoints = WaypointController(
            WaypointStore(self.get_parameter('maps_root').value),
            context=lambda: (
                self._sessions.mode,
                self._sessions.world,
                self._sessions.active_map,
            ),
            lookup_pose=self._lookup_pose,
            publish_goal=self._publish_goal,
        )
        self.create_service(
            Trigger, '/mapping/start', self.on_start_mapping, callback_group=group)
        self.create_service(
            Trigger, '/mapping/stop', self.on_stop_mapping, callback_group=group)
        self.create_service(
            Trigger, '/mapping/load', self.on_load_map, callback_group=group)
        self.create_service(
            Trigger, '/simulation/restart', self.on_restart_simulation,
            callback_group=group)
        self.create_service(
            Trigger, '/waypoints/save', self.on_save_waypoint,
            callback_group=group)
        self.create_service(
            Trigger, '/waypoints/navigate', self.on_navigate_waypoint,
            callback_group=group)
        self.create_service(
            Trigger, '/waypoints/delete', self.on_delete_waypoint,
            callback_group=group)
        self.create_timer(5.0, self.publish_state, callback_group=group)
        self.publish_state()
        self.get_logger().info('session_manager ready: IDLE (no map publisher)')

    def _start_child(self, role, command):
        self.get_logger().info(f'starting {role}: {" ".join(command)}')
        return ManagedProcess(command)

    def publish_state(self):
        self._state_pub.publish(String(data=self._sessions.mode))
        self._simulation_pub.publish(String(data=self._sessions.world))
        maps = self._sessions.available_maps()
        self._maps_pub.publish(String(data='\n'.join(maps) if maps else '<none>'))
        waypoint_names = []
        if self._sessions.mode == 'LOCALIZATION':
            try:
                waypoint_names = self._waypoints.names()
            except Exception as exc:
                self.get_logger().error(f'cannot list waypoints: {exc}')
        self._waypoint_pub.publish(String(data='\n'.join(waypoint_names)))

    def _result(self, response, action):
        try:
            with self._lock:
                message = action()
                self.publish_state()
            response.success = True
            response.message = message
        except Exception as exc:  # service boundary: surface exact operator error
            self.get_logger().error(str(exc))
            response.success = False
            response.message = str(exc)
            self.publish_state()
        return response

    def on_start_mapping(self, _request, response):
        name = self.get_parameter('map_name').value
        return self._result(response, lambda: self._start_mapping(name))

    def _start_mapping(self, name):
        self._sessions.start_mapping(name)
        return f'mapping started: {self._sessions.world}/{name}'

    def on_stop_mapping(self, _request, response):
        return self._result(response, self._stop_mapping)

    def _stop_mapping(self):
        path = self._sessions.stop_mapping(self._save_map)
        return f'map saved and mapping stopped: {path}.yaml'

    def on_load_map(self, _request, response):
        name = self.get_parameter('map_name').value
        return self._result(response, lambda: self._load_map(name))

    def _load_map(self, name):
        self._sessions.load_map(name)
        return f'localization started: {self._sessions.world}/{name}'

    def on_restart_simulation(self, _request, response):
        world = self.get_parameter('world').value
        return self._result(response, lambda: self._restart_simulation(world))

    def _restart_simulation(self, world):
        self._sessions.restart_simulation(world)
        return f'simulation restarted: {world}; navigation is IDLE'

    def on_save_waypoint(self, _request, response):
        name = self.get_parameter('waypoint_name').value
        return self._result(response, lambda: self._waypoints.save(name))

    def on_navigate_waypoint(self, _request, response):
        name = self.get_parameter('waypoint_name').value
        return self._result(response, lambda: self._waypoints.navigate(name))

    def on_delete_waypoint(self, _request, response):
        name = self.get_parameter('waypoint_name').value
        return self._result(response, lambda: self._waypoints.delete(name))

    def _lookup_pose(self):
        try:
            transform = self._tf_buffer.lookup_transform(
                'map', 'base_footprint', Time())
        except TransformException as exc:
            raise RuntimeError(
                f'map to base_footprint transform unavailable: {exc}') from exc
        translation = transform.transform.translation
        rotation = transform.transform.rotation
        yaw = math.atan2(
            2.0 * (rotation.w * rotation.z + rotation.x * rotation.y),
            1.0 - 2.0 * (rotation.y * rotation.y + rotation.z * rotation.z),
        )
        return Waypoint(translation.x, translation.y, yaw)

    def _publish_goal(self, waypoint):
        goal = PoseStamped()
        goal.header.frame_id = 'map'
        goal.header.stamp = self.get_clock().now().to_msg()
        goal.pose.position.x = waypoint.x
        goal.pose.position.y = waypoint.y
        goal.pose.orientation.z = math.sin(waypoint.yaw / 2.0)
        goal.pose.orientation.w = math.cos(waypoint.yaw / 2.0)
        self._goal_pub.publish(goal)

    def _save_map(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        if not self._save_client.wait_for_service(timeout_sec=5.0):
            raise RuntimeError('/slam_toolbox/save_map is unavailable')
        done = threading.Event()
        future = self._save_client.call_async(
            SaveMap.Request(name=String(data=str(path))))
        future.add_done_callback(lambda _future: done.set())
        if not done.wait(timeout=SERVICE_TIMEOUT_S):
            raise RuntimeError('saving map timed out')
        result = future.result()
        if result is None or result.result != 0:
            code = 'no response' if result is None else f'result={result.result}'
            raise RuntimeError(f'saving map failed: {code}')

    def destroy_node(self):
        self._sessions.close()
        return super().destroy_node()


def main(argv=None):
    rclpy.init(args=argv)
    node = SessionManager()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
