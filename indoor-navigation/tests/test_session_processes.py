import tempfile
import unittest
from pathlib import Path
import sys


APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT / 'src' / 'indoor_nav_bringup'))

from indoor_nav_bringup.session_processes import SessionProcesses  # noqa: E402


class FakeProcess:
    def __init__(self, role, command, events):
        self.role = role
        self.command = command
        self.events = events

    def stop(self):
        self.events.append(('stop', self.role))


class SessionProcessesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.events = []
        self.started = []

        def factory(role, command):
            process = FakeProcess(role, command, self.events)
            self.started.append(process)
            self.events.append(('start', role))
            return process

        self.sessions = SessionProcesses(factory, self.tmp.name, 'furnished_house')

    def tearDown(self):
        self.sessions.close()
        self.tmp.cleanup()

    def test_startup_runs_only_simulation_and_has_no_navigation_map_session(self):
        self.assertEqual(self.sessions.mode, 'IDLE')
        self.assertIsNone(self.sessions.active_map)
        self.assertEqual(self.sessions.world, 'furnished_house')
        self.assertEqual([process.role for process in self.started], ['simulation'])
        self.assertIn('world:=furnished_house', self.started[0].command)

    def test_mapping_start_and_stop_save_before_navigation_terminates(self):
        self.sessions.start_mapping('floor_1')
        self.assertEqual(self.sessions.mode, 'MAPPING')
        self.assertEqual(self.sessions.active_map, 'floor_1')
        navigation = self.started[-1]
        self.assertEqual(navigation.role, 'navigation')
        self.assertIn('mode:=mapping', navigation.command)

        saved = []

        def save(path):
            saved.append(path)
            self.events.append(('save', path))

        path = self.sessions.stop_mapping(save)
        self.assertEqual(path, Path(self.tmp.name) / 'furnished_house' / 'floor_1')
        self.assertEqual(saved, [path])
        self.assertLess(self.events.index(('save', path)), self.events.index(('stop', 'navigation')))
        self.assertEqual(self.sessions.mode, 'IDLE')
        self.assertIsNone(self.sessions.active_map)

    def test_loading_requires_a_saved_map_and_replaces_localization(self):
        with self.assertRaisesRegex(FileNotFoundError, 'missing'):
            self.sessions.load_map('missing')

        world_maps = Path(self.tmp.name) / 'furnished_house'
        world_maps.mkdir()
        (world_maps / 'office.yaml').write_text('image: office.pgm\n')
        self.sessions.load_map('office')
        self.assertEqual(self.sessions.mode, 'LOCALIZATION')
        self.assertEqual(self.sessions.active_map, 'office')
        self.assertIn(f'map_yaml:={world_maps / "office.yaml"}', self.started[-1].command)

        (world_maps / 'lobby.yaml').write_text('image: lobby.pgm\n')
        self.sessions.load_map('lobby')
        self.assertEqual(self.events[-2:], [('stop', 'navigation'), ('start', 'navigation')])
        self.assertEqual(self.sessions.available_maps(), ['lobby', 'office'])

    def test_world_restart_stops_navigation_then_simulation_and_returns_idle(self):
        world_maps = Path(self.tmp.name) / 'furnished_house'
        world_maps.mkdir()
        (world_maps / 'office.yaml').write_text('image: office.pgm\n')
        self.sessions.load_map('office')
        self.events.clear()

        self.sessions.restart_simulation('tugbot_warehouse')

        self.assertEqual(
            self.events,
            [('stop', 'navigation'), ('stop', 'simulation'), ('start', 'simulation')],
        )
        self.assertEqual(self.sessions.mode, 'IDLE')
        self.assertIsNone(self.sessions.active_map)
        self.assertEqual(self.sessions.world, 'tugbot_warehouse')
        self.assertIn('world:=tugbot_warehouse', self.started[-1].command)
        self.assertEqual(self.sessions.available_maps(), [])

    def test_rejects_unknown_worlds_and_unsafe_map_names(self):
        for world in ('house', 'arena', 'industrial_warehouse', 'mars'):
            with self.subTest(world=world), self.assertRaisesRegex(
                    ValueError, 'unknown world'):
                self.sessions.restart_simulation(world)
        with self.assertRaisesRegex(ValueError, 'map name'):
            self.sessions.start_mapping('../escape')


if __name__ == '__main__':
    unittest.main()
