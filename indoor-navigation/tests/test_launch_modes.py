import importlib.util
import unittest
from pathlib import Path
from unittest import mock

from launch import LaunchContext
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription
from launch.utilities import perform_substitutions


APP_ROOT = Path(__file__).resolve().parents[1]
LAUNCH_ROOT = APP_ROOT / 'src' / 'indoor_nav_bringup' / 'launch'


def load_launch(filename):
    path = LAUNCH_ROOT / filename
    spec = importlib.util.spec_from_file_location(filename, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def declared_names(description):
    return {
        entity.name for entity in description.entities
        if isinstance(entity, DeclareLaunchArgument)
    }


def render_parts(context, parts):
    return ''.join(part if isinstance(part, str)
                   else perform_substitutions(context, part)
                   for part in parts)


class LaunchModeTests(unittest.TestCase):
    def test_sim_preserves_world_selection_and_native_client(self):
        module = load_launch('sim.launch.py')
        with mock.patch.object(
                module, 'get_package_share_directory',
                side_effect=lambda package: f'/packages/{package}'):
            description = module.generate_launch_description()

        self.assertTrue({'world', 'gui'} <= declared_names(description))

        headless = LaunchContext()
        headless.launch_configurations.update(world='house', gui='false')
        headless_actions = module.gazebo_actions(
            headless, '/packages/turtlebot3_gazebo', '/packages/ros_gz_sim')
        headless_args = dict(headless_actions[0].launch_arguments)
        self.assertIn('turtlebot3_house.world',
                      render_parts(headless, headless_args['gz_args']))
        self.assertIn('--headless-rendering', ''.join(headless_args['gz_args']))
        self.assertFalse(any(isinstance(action, ExecuteProcess)
                             for action in headless_actions))

        native = LaunchContext()
        native.launch_configurations.update(world='arena', gui='true')
        native_actions = module.gazebo_actions(
            native, '/packages/turtlebot3_gazebo', '/packages/ros_gz_sim')
        native_args = dict(native_actions[0].launch_arguments)
        rendered = render_parts(native, native_args['gz_args'])
        self.assertIn('turtlebot3_world.world', rendered)
        self.assertNotIn('--headless-rendering', rendered)
        client = next(action for action in native_actions
                      if isinstance(action, ExecuteProcess))
        command = [perform_substitutions(native, part)
                   for part in client.process_description.cmd]
        self.assertEqual(command, ['gz', 'sim', '-g'])

    def test_nav_and_demo_forward_gui(self):
        for filename in ('nav.launch.py', 'demo.launch.py'):
            module = load_launch(filename)
            with mock.patch.object(module, 'get_package_share_directory',
                                   return_value='/packages/indoor_nav_bringup'):
                description = module.generate_launch_description()
            self.assertIn('gui', declared_names(description))
            include = next(entity for entity in description.entities
                           if isinstance(entity, IncludeLaunchDescription))
            arguments = dict(include.launch_arguments)
            context = LaunchContext()
            context.launch_configurations['gui'] = 'true'
            self.assertEqual(arguments['gui'].perform(context), 'true')

    def test_demo_gateway_script_is_portable(self):
        module = load_launch('demo.launch.py')
        with mock.patch.object(module, 'get_package_share_directory',
                               return_value='/packages/indoor_nav_bringup'):
            description = module.generate_launch_description()
        self.assertIn('gateway_script', declared_names(description))
        gateway = next(entity for entity in description.entities
                       if type(entity) is ExecuteProcess)
        context = LaunchContext()
        context.launch_configurations['gateway_script'] = '/app/gateway.py'
        command = [perform_substitutions(context, part)
                   for part in gateway.process_description.cmd]
        self.assertEqual(command, ['python3', '/app/gateway.py'])


if __name__ == '__main__':
    unittest.main()
