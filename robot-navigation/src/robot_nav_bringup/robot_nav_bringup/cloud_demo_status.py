"""Publish truthful hosted-demo readiness to the session gateway."""

import json
import os
import time

import rclpy
from rcl_interfaces.msg import Log
from rclpy.node import Node
from sensor_msgs.msg import LaserScan


STATUS_PATH = os.environ.get('DEMO_STATUS_PATH', '/tmp/demo_status.json')
VIEWER_INDEX = os.environ.get(
    'DEMO_VIEWER_INDEX', '/opt/lichtblick/index.html')
STARTED_AT = time.time()
SCAN_MAX_AGE_SECONDS = 5.0
LOG_LIMIT = 40
REQUIRED_NODES = {'session_manager', 'foxglove_bridge', 'ros_gz_bridge'}


def readiness(node_names, scan_age_seconds, viewer_ready):
    names = {name.strip('/') for name in node_names}
    missing = sorted(REQUIRED_NODES - names)
    if missing:
        return False, f'Waiting for {", ".join(missing)}'
    if scan_age_seconds is None or scan_age_seconds > SCAN_MAX_AGE_SECONDS:
        return False, 'Waiting for lidar'
    if not viewer_ready:
        return False, 'Waiting for Lichtblick'
    return True, 'Robot Navigation is ready'


class CloudDemoStatus(Node):
    def __init__(self):
        super().__init__('cloud_demo_status')
        self._last_scan_monotonic = None
        self._logs = []
        self._was_ready = False
        self.create_subscription(LaserScan, '/scan', self._on_scan, 10)
        self.create_subscription(Log, '/rosout', self._on_log, 20)
        self.create_timer(2.0, self._write)
        self._write()

    def _on_scan(self, _message):
        self._last_scan_monotonic = time.monotonic()

    def _on_log(self, message):
        line = f'[{message.name}] {message.msg}'[:200]
        self._logs.append(line)
        del self._logs[:-LOG_LIMIT]

    def _write(self):
        scan_age = None
        if self._last_scan_monotonic is not None:
            scan_age = time.monotonic() - self._last_scan_monotonic
        node_names = set(self.get_node_names())
        ready, message = readiness(
            node_names, scan_age, os.path.isfile(VIEWER_INDEX))
        payload = {
            'start': STARTED_AT,
            'ready': ready,
            'phase': 'READY' if ready else 'BOOTING',
            'message': message,
            'rtf': None,
            'nodes': len(node_names),
            'log': (self._logs or [message])[-LOG_LIMIT:],
        }
        temporary = f'{STATUS_PATH}.tmp'
        with open(temporary, 'w', encoding='utf-8') as handle:
            json.dump(payload, handle)
        os.replace(temporary, STATUS_PATH)
        if ready and not self._was_ready:
            self.get_logger().info('DEMO READY')
            print('DEMO READY', flush=True)
        self._was_ready = ready


def main():
    rclpy.init()
    node = CloudDemoStatus()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
