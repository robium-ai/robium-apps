import unittest
from pathlib import Path

import yaml


APP_ROOT = Path(__file__).resolve().parents[1]


class RobotProfileTests(unittest.TestCase):
    def test_waffle_pi_is_the_only_configured_robot(self):
        compose = yaml.safe_load((APP_ROOT / 'docker' / 'compose.yaml').read_text())
        app = yaml.safe_load((APP_ROOT / 'robium-app.yaml').read_text())

        self.assertEqual(compose['x-app']['environment']['TURTLEBOT3_MODEL'], 'waffle_pi')
        self.assertEqual(
            compose['services']['smoke']['environment']['TURTLEBOT3_MODEL'],
            'waffle_pi',
        )
        self.assertEqual(
            app['demo']['orchestrator']['env']['TURTLEBOT3_MODEL'],
            'waffle_pi',
        )
        self.assertIn(
            'WORLD:-furnished_house', compose['services']['mapping']['command'])

    def test_nav2_costmaps_use_the_upstream_waffle_pi_radius(self):
        config = yaml.safe_load(
            (APP_ROOT / 'src' / 'indoor_nav_bringup' / 'config' /
             'nav2_params.yaml').read_text()
        )

        local = config['local_costmap']['local_costmap']['ros__parameters']
        global_costmap = config['global_costmap']['global_costmap']['ros__parameters']
        self.assertEqual(local['robot_radius'], 0.15)
        self.assertEqual(global_costmap['robot_radius'], 0.15)


if __name__ == '__main__':
    unittest.main()
