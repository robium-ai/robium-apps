#!/usr/bin/env python3
"""Contract tests for the lightweight default simulation world."""

import importlib.util
import json
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET


APP_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = APP_ROOT / 'src' / 'robot_nav_bringup'
WORLD_PATH = PACKAGE_ROOT / 'worlds' / 'simple_house.world'


def load_session_processes():
    path = PACKAGE_ROOT / 'robot_nav_bringup' / 'session_processes.py'
    spec = importlib.util.spec_from_file_location('session_processes', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeProcess:
    def stop(self):
        pass


class SimpleHouseTests(unittest.TestCase):
    def test_world_is_small_and_self_contained(self):
        root = ET.parse(WORLD_PATH).getroot()
        world = root.find('world')
        self.assertIsNotNone(world)

        models = world.findall('model')
        self.assertEqual([model.get('name') for model in models], [
            'ground_plane',
            'simple_house',
        ])
        house = models[1]
        self.assertEqual(len(house.findall('link')), 12)
        self.assertEqual(root.findall('.//mesh'), [])
        self.assertEqual(root.findall('.//include'), [])

        plugins = {plugin.get('name') for plugin in world.findall('plugin')}
        self.assertTrue({
            'gz::sim::systems::Physics',
            'gz::sim::systems::UserCommands',
            'gz::sim::systems::SceneBroadcaster',
            'gz::sim::systems::Sensors',
            'gz::sim::systems::Imu',
        }.issubset(plugins))

    def test_session_manager_defaults_to_simple_house(self):
        session_processes = load_session_processes()
        starts = []

        def factory(role, command):
            starts.append((role, command))
            return FakeProcess()

        sessions = session_processes.SessionProcesses(factory, '/tmp/maps')
        self.assertEqual(sessions.world, 'simple_house')
        self.assertEqual(starts[0][0], 'simulation')
        self.assertIn('world:=simple_house', starts[0][1])
        self.assertEqual(session_processes.WORLD_NAMES, (
            'simple_house',
            'furnished_house',
            'tugbot_warehouse',
        ))

    def test_default_spawn_clears_every_house_collision(self):
        root = ET.parse(WORLD_PATH).getroot()
        house = root.find(".//model[@name='simple_house']")
        spawn_x, spawn_y = -2.0, -0.5
        clearance = 0.20  # Waffle Pi radius (0.15 m) plus spawn margin.

        for link in house.findall('link'):
            x, y, *_ = map(float, link.findtext('pose').split())
            sx, sy, *_ = map(
                float, link.findtext('collision/geometry/box/size').split())
            inside_expanded_box = (
                abs(spawn_x - x) <= sx / 2 + clearance
                and abs(spawn_y - y) <= sy / 2 + clearance
            )
            self.assertFalse(
                inside_expanded_box,
                f'default spawn intersects {link.get("name")}',
            )

    def test_dashboard_lists_simple_house_first(self):
        layout = json.loads((APP_ROOT / 'lichtblick' / 'layout.json').read_text())
        worlds = layout['configById']['Robium Dashboard.dashboard!control'][
            'simulationWorlds']
        self.assertEqual(worlds, [
            {'value': 'simple_house', 'label': 'Simple House'},
            {'value': 'furnished_house', 'label': 'Furnished House'},
            {'value': 'tugbot_warehouse', 'label': 'Warehouse'},
        ])

    def test_every_startup_path_uses_the_lightweight_default(self):
        compose = (APP_ROOT / 'docker' / 'compose.yaml').read_text()
        launcher = (APP_ROOT / 'app').read_text()
        sim_launch = (PACKAGE_ROOT / 'launch' / 'sim.launch.py').read_text()
        mapping_launch = (
            PACKAGE_ROOT / 'launch' / 'mapping.launch.py').read_text()
        cloud_launch = (
            PACKAGE_ROOT / 'launch' / 'cloud_demo.launch.py').read_text()
        session_manager = (
            PACKAGE_ROOT / 'robot_nav_bringup' / 'session_manager.py').read_text()

        self.assertEqual(compose.count('WORLD:-simple_house'), 2)
        self.assertIn('WORLD:-simple_house', launcher)
        self.assertIn("default_value='simple_house'", sim_launch)
        self.assertIn("default_value='simple_house'", mapping_launch)
        self.assertIn("'world': 'simple_house'", cloud_launch)
        self.assertIn("declare_parameter('world', 'simple_house')", session_manager)


if __name__ == '__main__':
    unittest.main()
