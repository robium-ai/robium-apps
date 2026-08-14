#!/usr/bin/env python3
"""ROS services that manage the dashboard's simulator and map sessions."""

import os
import signal
import subprocess
import threading

import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from slam_toolbox.srv import SaveMap
from std_msgs.msg import String
from std_srvs.srv import Trigger

from .session_processes import SessionProcesses


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
        self._lock = threading.RLock()
        group = ReentrantCallbackGroup()

        self._state_pub = self.create_publisher(String, '/mapping/state', LATCHED)
        self._maps_pub = self.create_publisher(String, '/maps/available', LATCHED)
        self._simulation_pub = self.create_publisher(
            String, '/simulation/state', LATCHED)
        self._save_client = self.create_client(
            SaveMap, '/slam_toolbox/save_map', callback_group=group)

        self._sessions = SessionProcesses(
            lambda role, command: self._start_child(role, command),
            self.get_parameter('maps_root').value,
            self.get_parameter('world').value,
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
