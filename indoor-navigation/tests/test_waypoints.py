import json
import math
from pathlib import Path
import sys
import tempfile
import unittest


APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT / 'src' / 'indoor_nav_bringup'))

from indoor_nav_bringup.waypoints import (  # noqa: E402
    Waypoint,
    WaypointController,
    WaypointStore,
)


class WaypointStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = WaypointStore(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_round_trips_sorted_waypoints_in_a_versioned_sidecar(self):
        self.store.save(
            'furnished_house', 'office', 'Lobby', Waypoint(1.0, 2.0, 0.5))
        self.store.save(
            'furnished_house', 'office', 'Kitchen', Waypoint(-3.0, 4.5, -1.25))

        self.assertEqual(
            self.store.list_names('furnished_house', 'office'),
            ['Kitchen', 'Lobby'],
        )
        self.assertEqual(
            self.store.get('furnished_house', 'office', 'Kitchen'),
            Waypoint(-3.0, 4.5, -1.25),
        )
        sidecar = self.root / 'furnished_house' / 'office.waypoints.json'
        self.assertEqual(
            json.loads(sidecar.read_text(encoding='utf-8')),
            {
                'version': 1,
                'waypoints': {
                    'Kitchen': {'x': -3.0, 'y': 4.5, 'yaw': -1.25},
                    'Lobby': {'x': 1.0, 'y': 2.0, 'yaw': 0.5},
                },
            },
        )
        self.assertFalse(sidecar.with_suffix(sidecar.suffix + '.tmp').exists())

    def test_scopes_waypoints_to_the_world_and_map(self):
        self.store.save(
            'furnished_house', 'office', 'Kitchen', Waypoint(1.0, 2.0, 0.0))

        self.assertEqual(self.store.list_names('furnished_house', 'warehouse'), [])
        self.assertEqual(self.store.list_names('tugbot_warehouse', 'office'), [])

    def test_rejects_duplicate_unsafe_and_non_finite_values_without_overwrite(self):
        original = Waypoint(1.0, 2.0, 0.5)
        self.store.save('furnished_house', 'office', 'Kitchen', original)

        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.store.save(
                'furnished_house', 'office', 'Kitchen', Waypoint(9.0, 9.0, 0.0))
        self.assertEqual(
            self.store.get('furnished_house', 'office', 'Kitchen'), original)

        for token in ('../office', 'floor/office', '', 'a' * 65):
            with self.subTest(token=token), self.assertRaisesRegex(ValueError, 'name'):
                self.store.list_names('furnished_house', token)
        for value in (math.inf, -math.inf, math.nan):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'finite'):
                self.store.save(
                    'furnished_house', 'office', 'BadPose', Waypoint(value, 0.0, 0.0))

    def test_refuses_malformed_sidecars_without_replacing_them(self):
        sidecar = self.root / 'furnished_house' / 'office.waypoints.json'
        sidecar.parent.mkdir(parents=True)
        malformed = '{"version": 1, "waypoints": {"Kitchen": {"x": "bad"}}}'
        sidecar.write_text(malformed, encoding='utf-8')

        with self.assertRaisesRegex(ValueError, 'invalid waypoint sidecar'):
            self.store.save(
                'furnished_house', 'office', 'Lobby', Waypoint(1.0, 2.0, 0.0))
        self.assertEqual(sidecar.read_text(encoding='utf-8'), malformed)

    def test_delete_removes_only_the_requested_waypoint_and_empty_sidecar(self):
        self.store.save(
            'furnished_house', 'office', 'Kitchen', Waypoint(1.0, 2.0, 0.0))
        self.store.save(
            'furnished_house', 'office', 'Lobby', Waypoint(3.0, 4.0, 1.0))

        self.store.delete('furnished_house', 'office', 'Kitchen')
        self.assertEqual(self.store.list_names('furnished_house', 'office'), ['Lobby'])
        with self.assertRaisesRegex(KeyError, 'Missing'):
            self.store.get('furnished_house', 'office', 'Missing')
        with self.assertRaisesRegex(KeyError, 'Missing'):
            self.store.delete('furnished_house', 'office', 'Missing')

        self.store.delete('furnished_house', 'office', 'Lobby')
        self.assertEqual(self.store.list_names('furnished_house', 'office'), [])
        self.assertFalse(
            (self.root / 'furnished_house' / 'office.waypoints.json').exists())


class WaypointControllerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.context = ['LOCALIZATION', 'furnished_house', 'office']
        self.published = []
        self.controller = WaypointController(
            WaypointStore(self.root),
            context=lambda: tuple(self.context),
            lookup_pose=lambda: Waypoint(1.0, 2.0, 0.5),
            publish_goal=self.published.append,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_saves_the_current_pose_and_publishes_a_stored_goal(self):
        self.assertIn('saved waypoint', self.controller.save('Kitchen'))
        self.assertEqual(self.controller.names(), ['Kitchen'])

        self.assertIn('navigation requested', self.controller.navigate('Kitchen'))
        self.assertEqual(self.published, [Waypoint(1.0, 2.0, 0.5)])

    def test_refuses_all_actions_outside_localization(self):
        for mode in ('IDLE', 'MAPPING'):
            self.context[0] = mode
            for action in (
                lambda: self.controller.save('Kitchen'),
                lambda: self.controller.navigate('Kitchen'),
                lambda: self.controller.delete('Kitchen'),
            ):
                with self.subTest(mode=mode, action=action), self.assertRaisesRegex(
                        RuntimeError, 'LOCALIZATION'):
                    action()
        self.assertFalse(any(self.root.rglob('*.waypoints.json')))

    def test_missing_transform_does_not_create_a_waypoint(self):
        def missing_pose():
            raise RuntimeError('map to base_footprint transform unavailable')

        controller = WaypointController(
            WaypointStore(self.root),
            context=lambda: tuple(self.context),
            lookup_pose=missing_pose,
            publish_goal=self.published.append,
        )
        with self.assertRaisesRegex(RuntimeError, 'transform unavailable'):
            controller.save('Kitchen')
        self.assertFalse(any(self.root.rglob('*.waypoints.json')))

    def test_deletes_one_waypoint_and_rejects_unknown_names(self):
        self.controller.save('Kitchen')
        self.assertIn('deleted waypoint', self.controller.delete('Kitchen'))
        self.assertEqual(self.controller.names(), [])

        with self.assertRaisesRegex(KeyError, 'Missing'):
            self.controller.navigate('Missing')
        with self.assertRaisesRegex(KeyError, 'Missing'):
            self.controller.delete('Missing')


if __name__ == '__main__':
    unittest.main()
