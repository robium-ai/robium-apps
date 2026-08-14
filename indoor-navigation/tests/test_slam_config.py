import unittest
from pathlib import Path

import yaml


APP_ROOT = Path(__file__).resolve().parents[1]


class SlamConfigTests(unittest.TestCase):
    def test_map_updates_fit_inside_slam_toolbox_save_timeout(self):
        config = yaml.safe_load(
            (APP_ROOT / 'src' / 'indoor_nav_bringup' / 'config' /
             'slam_params.yaml').read_text()
        )
        interval = config['slam_toolbox']['ros__parameters']['map_update_interval']
        self.assertLessEqual(interval, 1.0)


if __name__ == '__main__':
    unittest.main()
