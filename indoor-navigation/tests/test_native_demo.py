import json
import os
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.native_paths import NativePaths


class NativeDemoTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.app_root = Path(self.temporary_directory.name).resolve()
        self.paths = NativePaths.from_app_root(self.app_root)

    def test_launch_command_uses_local_pixi_overlay_and_native_arguments(self):
        from scripts.native_demo import launch_command

        command = launch_command(self.paths)
        self.assertEqual(command[0], str(self.paths.pixi))
        self.assertIn(str(self.paths.experiment / 'pixi.toml'), command)
        self.assertIn(str(self.paths.install / 'setup.sh'), command)
        self.assertIn(str(self.app_root / 'scripts' / 'demo_gateway.py'), command)
        shell_program = command[command.index('-c') + 1]
        self.assertIn('ros2 launch indoor_nav_bringup demo.launch.py', shell_program)
        self.assertIn('gui:=true', shell_program)
        self.assertIn('gateway_script:=$2', shell_program)

    def test_build_uses_symlink_mode_with_compatible_setuptools_pin(self):
        from scripts.native_demo import build_command

        command = build_command(self.paths)
        self.assertIn('--symlink-install', command)

    def test_opengl_probe_warning_is_not_fatal_when_metal_follows(self):
        from scripts.native_demo import renderer_failure

        self.assertFalse(renderer_failure(
            'Unable to load Ogre Plugin[/env/lib/OGRE-Next]'))
        self.assertFalse(renderer_failure('Rendering will not be possible.'))
        self.assertFalse(renderer_failure('Loading plugin [gz-rendering-ogre2]'))

    def test_actual_metal_render_failure_is_fatal(self):
        from scripts.native_demo import renderer_failure

        self.assertTrue(renderer_failure(
            'RenderTextureMetalId is not supported by current render engine'))

    def test_stop_targets_only_validated_process_group(self):
        from scripts.native_demo import stop_owned_process

        self.paths.runtime.mkdir(parents=True)
        self.paths.process_metadata.write_text(json.dumps({
            'pid': 123,
            'pgid': 456,
            'app_root': str(self.app_root),
            'started_at': 1,
        }))
        with mock.patch('scripts.native_paths.os.kill'), \
                mock.patch('scripts.native_demo.os.killpg') as killpg, \
                mock.patch('scripts.native_demo._process_group_alive',
                           side_effect=[True, False]), \
                mock.patch('scripts.native_demo.time.sleep'):
            self.assertTrue(stop_owned_process(self.paths))
        killpg.assert_called_once_with(456, signal.SIGINT)
        self.assertNotEqual(killpg.call_args.args[0], 1)

    def test_mismatched_metadata_never_signals(self):
        from scripts.native_demo import stop_owned_process

        self.paths.runtime.mkdir(parents=True)
        self.paths.process_metadata.write_text(json.dumps({
            'pid': 123,
            'pgid': 456,
            'app_root': '/different-app',
            'started_at': 1,
        }))
        with mock.patch('scripts.native_demo.os.killpg') as killpg:
            self.assertFalse(stop_owned_process(self.paths))
        killpg.assert_not_called()
        self.assertFalse(self.paths.process_metadata.exists())

    def test_process_group_permission_error_is_treated_as_not_controllable(self):
        from scripts.native_demo import _process_group_alive

        with mock.patch('scripts.native_demo.os.killpg',
                        side_effect=PermissionError):
            self.assertFalse(_process_group_alive(456))

    def test_direct_script_entry_point_can_import_helpers(self):
        result = subprocess.run(
            [sys.executable, 'scripts/native_demo.py', '--help'],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('run', result.stdout)
        self.assertIn('down', result.stdout)


if __name__ == '__main__':
    unittest.main()
