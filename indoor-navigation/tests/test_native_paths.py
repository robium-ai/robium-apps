import json
import socket
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class NativePathsTests(unittest.TestCase):
    def setUp(self):
        from scripts.native_paths import NativePaths

        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.app_root = Path(self.temporary_directory.name).resolve()
        self.paths = NativePaths.from_app_root(self.app_root)

    def test_every_runtime_path_is_contained(self):
        for value in self.paths.runtime_paths():
            self.assertTrue(value.is_relative_to(self.paths.runtime), value)

    def test_environment_redirects_all_user_state(self):
        from scripts.native_paths import native_environment

        env = native_environment(self.paths, {'PATH': '/usr/bin'})

        self.assertEqual(env['PIXI_HOME'], str(self.paths.pixi_home))
        self.assertEqual(env['PIXI_CACHE_DIR'], str(self.paths.cache))
        self.assertEqual(env['RATTLER_CACHE_DIR'], str(self.paths.cache))
        self.assertEqual(env['TMPDIR'], str(self.paths.tmp))
        self.assertEqual(env['ROS_HOME'], str(self.paths.ros_home))
        self.assertEqual(env['ROS_LOG_DIR'], str(self.paths.ros_logs))
        self.assertEqual(env['GZ_HOMEDIR'], str(self.paths.gz_home))
        self.assertEqual(env['COLCON_HOME'], str(self.paths.colcon_home))
        self.assertEqual(env['DEMO_STATUS_PATH'], str(self.paths.status))
        self.assertEqual(env['DEMO_STATIC_ROOT'], str(self.paths.viewer))
        self.assertEqual(env['DEMO_SHUTDOWN_MODE'], 'parent')
        self.assertEqual(env['RMW_IMPLEMENTATION'], 'rmw_cyclonedds_cpp')
        self.assertEqual(env['ROS_DOMAIN_ID'], '42')
        self.assertEqual(env['TURTLEBOT3_MODEL'], 'burger_cam')
        self.assertEqual(env['HOME'], str(self.paths.runtime_home))

    def test_environment_does_not_forward_common_secret_variables(self):
        from scripts.native_paths import native_environment

        env = native_environment(self.paths, {
            'PATH': '/usr/bin',
            'DOPPLER_TOKEN': 'secret',
            'EXAMPLE_API_KEY': 'secret',
            'DATABASE_PASSWORD': 'secret',
        })

        self.assertNotIn('DOPPLER_TOKEN', env)
        self.assertNotIn('EXAMPLE_API_KEY', env)
        self.assertNotIn('DATABASE_PASSWORD', env)
        self.assertEqual(env['PATH'], '/usr/bin')

    def test_listening_port_is_rejected(self):
        from scripts.native_paths import NativeError, require_free_ports

        listener = socket.socket()
        self.addCleanup(listener.close)
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        port = listener.getsockname()[1]

        with self.assertRaisesRegex(NativeError, f'port {port} is already in use'):
            require_free_ports([port])

    def test_recently_released_port_is_not_reported_as_busy(self):
        from scripts.native_paths import require_free_ports

        listener = socket.socket()
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        port = listener.getsockname()[1]
        client = socket.create_connection(('127.0.0.1', port))
        connection, _ = listener.accept()
        connection.close()
        client.close()
        listener.close()

        require_free_ports([port])

    def test_owned_process_requires_matching_app_root(self):
        from scripts.native_paths import read_owned_process

        self.paths.runtime.mkdir(parents=True)
        self.paths.process_metadata.write_text(json.dumps({
            'pid': 123,
            'pgid': 123,
            'app_root': '/another-app',
            'started_at': 1,
        }))

        self.assertIsNone(read_owned_process(self.paths))

    def test_owned_process_returns_live_matching_metadata(self):
        from scripts.native_paths import OwnedProcess, read_owned_process

        self.paths.runtime.mkdir(parents=True)
        self.paths.process_metadata.write_text(json.dumps({
            'pid': 123,
            'pgid': 456,
            'app_root': str(self.app_root),
            'started_at': 1,
        }))

        with mock.patch('scripts.native_paths.os.kill') as kill:
            self.assertEqual(
                read_owned_process(self.paths),
                OwnedProcess(pid=123, pgid=456, app_root=self.app_root,
                             started_at=1.0),
            )
            kill.assert_called_once_with(123, 0)

    def test_malformed_process_metadata_is_ignored(self):
        from scripts.native_paths import read_owned_process

        self.paths.runtime.mkdir(parents=True)
        self.paths.process_metadata.write_text('{not json')
        self.assertIsNone(read_owned_process(self.paths))


if __name__ == '__main__':
    unittest.main()
