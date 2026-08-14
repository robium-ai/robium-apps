import importlib.util
import os
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

from launch import LaunchContext
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription
from launch_ros.actions import Node
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
    def test_sim_resolves_all_dashboard_worlds_to_pinned_assets_and_spawn_poses(self):
        module = load_launch('sim.launch.py')
        local = module.world_spec('/bringup', '/tb3', 'house')
        tugbot = module.world_spec('/bringup', '/tb3', 'tugbot_warehouse')
        industrial = module.world_spec('/bringup', '/tb3', 'industrial_warehouse')
        try:
            furnished = module.world_spec('/bringup', '/tb3', 'furnished_house')
        except ValueError as error:
            self.fail(f'Furnished House is not routed: {error}')

        self.assertEqual(local, ('/bringup/worlds/turtlebot3_house.world', '-2.0', '-0.5'))
        self.assertEqual(
            tugbot,
            ('https://fuel.gazebosim.org/1.0/OpenRobotics/worlds/'
             'Tugbot%20in%20Warehouse/2', '0.0', '0.0'),
        )
        self.assertEqual(
            industrial,
            ('https://fuel.gazebosim.org/1.0/OpenRobotics/worlds/'
             'industrial-warehouse/4', '0.0', '0.0'),
        )
        self.assertEqual(
            furnished,
            ('/opt/robium/worlds/aws-small-house/worlds/small_house.world',
             '3.5', '1.0'),
        )

    def test_sim_preserves_world_selection_and_native_client(self):
        module = load_launch('sim.launch.py')
        with mock.patch.object(
                module, 'get_package_share_directory',
                side_effect=lambda package: f'/packages/{package}'):
            description = module.generate_launch_description()

        self.assertTrue({'world', 'gui', 'bridge'} <= declared_names(description))

        headless = LaunchContext()
        headless.launch_configurations.update(world='house', gui='false', bridge='true')
        headless_actions = module.gazebo_actions(
            headless, '/packages/indoor_nav_bringup',
            '/packages/turtlebot3_gazebo', '/packages/ros_gz_sim')
        headless_args = dict(headless_actions[0].launch_arguments)
        self.assertIn('turtlebot3_house.world',
                      render_parts(headless, headless_args['gz_args']))
        self.assertIn('/packages/indoor_nav_bringup/worlds/',
                      render_parts(headless, headless_args['gz_args']))
        self.assertIn('--headless-rendering', ''.join(headless_args['gz_args']))
        self.assertFalse(any(isinstance(action, ExecuteProcess)
                             for action in headless_actions))

        native = LaunchContext()
        native.launch_configurations.update(world='arena', gui='true', bridge='true')
        native_actions = module.gazebo_actions(
            native, '/packages/indoor_nav_bringup',
            '/packages/turtlebot3_gazebo', '/packages/ros_gz_sim')
        native_args = dict(native_actions[0].launch_arguments)
        rendered = render_parts(native, native_args['gz_args'])
        self.assertIn('turtlebot3_world.world', rendered)
        self.assertNotIn('--headless-rendering', rendered)
        client = next(action for action in native_actions
                      if isinstance(action, ExecuteProcess))
        command = [perform_substitutions(native, part)
                   for part in client.process_description.cmd]
        self.assertEqual(command, ['gz', 'sim', '-g'])

    def test_furnished_house_launch_adds_modern_gazebo_systems(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            asset = Path(temporary_directory) / 'aws-small-house'
            source_world = asset / 'worlds' / 'small_house.world'
            source_world.parent.mkdir(parents=True)
            shoe_model = (
                asset / 'models' / 'aws_robomaker_residential_ShoeRack_01' /
                'model.sdf'
            )
            shoe_model.parent.mkdir(parents=True)
            shoe_model.write_text(
                '<sdf><model><link><inertial><inertia>'
                '<ixx>0.02</ixx><iyy>0.04</iyy><ixx>0.02</ixx>'
                '</inertia></inertial></link></model></sdf>'
            )
            portrait_mesh = (
                asset / 'models' / 'aws_robomaker_residential_PortraitA_01' /
                'meshes' / 'portrait.dae'
            )
            portrait_mesh.parent.mkdir(parents=True)
            portrait_mesh.write_text(
                '<COLLADA><image><init_from>'
                '../../../../photos/PortraitA_01.jpg'
                '</init_from></image></COLLADA>'
            )
            source_world.write_text('<sdf version="1.6"><world name="default"/></sdf>')
            with mock.patch.dict(os.environ, {'AWS_SMALL_HOUSE_ROOT': str(asset)}):
                module = load_launch('sim.launch.py')
            context = LaunchContext()
            context.launch_configurations.update(
                world='furnished_house', gui='false', bridge='true')
            try:
                actions = module.gazebo_actions(
                    context, '/bringup', '/tb3', '/ros_gz_sim')
            except ValueError as error:
                self.fail(f'Furnished House launch is not implemented: {error}')

            arguments = dict(actions[0].launch_arguments)
            rendered = render_parts(context, arguments['gz_args'])
            prepared_world = source_world.with_name('small_house.robium.world')
            self.assertIn(str(prepared_world), rendered)
            repaired_root = ET.parse(prepared_world).getroot()
            plugin_names = {
                plugin.get('name') for plugin in repaired_root.findall('.//world/plugin')
            }
            self.assertIn('gz::sim::systems::Sensors', plugin_names)
            self.assertIn('gz::sim::systems::Imu', plugin_names)
            shoe_inertia = ET.parse(shoe_model).getroot().find('.//inertia')
            self.assertIsNotNone(shoe_inertia)
            self.assertEqual(
                [child.tag for child in shoe_inertia], ['ixx', 'iyy', 'izz'])
            self.assertIn(
                '../../../photos/PortraitA_01.jpg', portrait_mesh.read_text())
            self.assertNotIn(
                '../../../../photos/', portrait_mesh.read_text())
            self.assertEqual(
                source_world.read_text(),
                '<sdf version="1.6"><world name="default"/></sdf>',
            )

    def test_mapping_dashboard_starts_a_session_manager_without_a_map_stack(self):
        module = load_launch('mapping.launch.py')
        description = module.generate_launch_description()

        self.assertTrue({'world', 'map_name'} <= declared_names(description))
        self.assertFalse(any(isinstance(entity, IncludeLaunchDescription)
                             for entity in description.entities))
        nodes = [entity for entity in description.entities if isinstance(entity, Node)]
        executables = {node.node_executable for node in nodes}
        self.assertIn('session_manager', executables)
        self.assertIn('teleop_relay', executables)
        self.assertIn('foxglove_bridge', executables)

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
