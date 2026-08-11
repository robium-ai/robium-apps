import importlib.util
import os
import signal
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


APP_ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ros_stubs():
    modules = {}
    rclpy = types.ModuleType('rclpy')
    modules['rclpy'] = rclpy
    for module_name, class_name in (
        ('geometry_msgs.msg', 'PoseStamped'),
        ('nav2_simple_commander.robot_navigator', 'BasicNavigator'),
        ('nav_msgs.msg', 'Odometry'),
        ('rcl_interfaces.msg', 'Log'),
    ):
        module = types.ModuleType(module_name)
        setattr(module, class_name, type(class_name, (), {}))
        modules[module_name] = module
        package = module_name.split('.')[0]
        modules.setdefault(package, types.ModuleType(package))
    return modules


class GatewayPortabilityTests(unittest.TestCase):
    def load_gateway(self, env=None):
        with mock.patch.dict(os.environ, env or {}, clear=True):
            return load_module(
                f'demo_gateway_{self.id()}',
                APP_ROOT / 'scripts' / 'demo_gateway.py',
            )

    def test_container_defaults_are_preserved(self):
        gateway = self.load_gateway()
        self.assertEqual(gateway.STATIC_ROOT, '/opt/lichtblick')
        self.assertEqual(gateway.STATUS_PATH, '/tmp/demo_status.json')
        self.assertEqual(gateway.BRIDGE, ('127.0.0.1', 8766))
        self.assertEqual(gateway.SHUTDOWN_MODE, 'pid1')

    def test_native_environment_overrides_paths_bridge_and_shutdown(self):
        gateway = self.load_gateway({
            'DEMO_STATIC_ROOT': '/app/runtime/viewer',
            'DEMO_STATUS_PATH': '/app/runtime/status.json',
            'DEMO_BRIDGE_HOST': 'localhost',
            'DEMO_BRIDGE_PORT': '9999',
            'DEMO_SHUTDOWN_MODE': 'parent',
        })
        self.assertEqual(gateway.STATIC_ROOT, '/app/runtime/viewer')
        self.assertEqual(gateway.STATUS_PATH, '/app/runtime/status.json')
        self.assertEqual(gateway.BRIDGE, ('localhost', 9999))
        self.assertEqual(gateway.SHUTDOWN_MODE, 'parent')

    def test_shutdown_signals_pid1_in_container_mode(self):
        gateway = self.load_gateway()
        with mock.patch.object(gateway.os, 'kill') as kill:
            gateway.signal_shutdown('pid1')
        kill.assert_called_once_with(1, signal.SIGINT)

    def test_shutdown_signals_parent_in_native_mode(self):
        gateway = self.load_gateway()
        with mock.patch.object(gateway.os, 'getppid', return_value=321), \
                mock.patch.object(gateway.os, 'kill') as kill:
            gateway.signal_shutdown('parent')
        kill.assert_called_once_with(321, signal.SIGINT)

    def test_invalid_shutdown_mode_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'DEMO_SHUTDOWN_MODE'):
            self.load_gateway({'DEMO_SHUTDOWN_MODE': 'all'})


class DemoInitPortabilityTests(unittest.TestCase):
    def load_demo_init(self, env=None):
        with mock.patch.dict(sys.modules, ros_stubs()), \
                mock.patch.dict(os.environ, env or {}, clear=True):
            return load_module(
                f'demo_init_{self.id()}',
                APP_ROOT / 'src' / 'indoor_nav_bringup' /
                'indoor_nav_bringup' / 'demo_init.py',
            )

    def test_container_defaults_are_preserved(self):
        demo_init = self.load_demo_init()
        self.assertEqual(demo_init.STATUS_PATH, '/tmp/demo_status.json')
        self.assertEqual(demo_init.SHUTDOWN_MODE, 'pid1')

    def test_native_status_and_parent_shutdown_are_supported(self):
        demo_init = self.load_demo_init({
            'DEMO_STATUS_PATH': '/app/runtime/status.json',
            'DEMO_SHUTDOWN_MODE': 'parent',
        })
        self.assertEqual(demo_init.STATUS_PATH, '/app/runtime/status.json')
        with mock.patch.object(demo_init.os, 'getppid', return_value=654), \
                mock.patch.object(demo_init.os, 'kill') as kill:
            demo_init.signal_shutdown('parent')
        kill.assert_called_once_with(654, signal.SIGINT)


if __name__ == '__main__':
    unittest.main()
