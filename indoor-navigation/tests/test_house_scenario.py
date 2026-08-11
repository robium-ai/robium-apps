import importlib
import json
import unittest
from pathlib import Path

import yaml


APP_ROOT = Path(__file__).resolve().parents[1]
MAP_YAML = APP_ROOT / 'src' / 'indoor_nav_bringup' / 'maps' / 'map.yaml'


def read_pgm(path):
    data = path.read_bytes()
    index = 0
    tokens = []
    while len(tokens) < 4:
        while index < len(data) and chr(data[index]).isspace():
            index += 1
        if data[index:index + 1] == b'#':
            index = data.index(b'\n', index) + 1
            continue
        end = index
        while end < len(data) and not chr(data[end]).isspace():
            end += 1
        tokens.append(data[index:end])
        index = end
    while index < len(data) and chr(data[index]).isspace():
        index += 1
    magic, width, height, maximum = tokens
    if magic != b'P5' or maximum != b'255':
        raise AssertionError('expected an 8-bit binary PGM')
    return int(width), int(height), data[index:index + int(width) * int(height)]


class HouseScenarioTests(unittest.TestCase):
    def test_house_map_covers_initial_pose_and_default_goals(self):
        send_goals = importlib.import_module('indoor_nav_bringup.send_goals')
        mapping_route = importlib.import_module(
            'indoor_nav_bringup.drive_mapping_route')
        metadata = yaml.safe_load(MAP_YAML.read_text())
        width, height, pixels = read_pgm(MAP_YAML.parent / metadata['image'])
        self.assertGreaterEqual(width, 220)
        self.assertGreaterEqual(height, 140)
        self.assertEqual(mapping_route.SCENARIO, 'turtlebot3_house')
        origin_x, origin_y, _ = metadata['origin']
        resolution = float(metadata['resolution'])
        points = [send_goals.INITIAL_POSE]
        points.extend(tuple(map(float, item.split(',')))
                      for item in send_goals.DEFAULT_GOALS.split(';'))
        for x, y in points:
            column = int((x - origin_x) / resolution)
            row = height - 1 - int((y - origin_y) / resolution)
            self.assertTrue(0 <= column < width and 0 <= row < height)
            self.assertGreaterEqual(pixels[row * width + column], 250)

    def test_layouts_use_robot_camera_and_never_overhead_camera(self):
        layouts = [
            APP_ROOT / 'foxglove' / 'indoor-navigation-layout.json',
            APP_ROOT / 'lichtblick' / 'nav-layout.json',
            APP_ROOT / 'lichtblick' / 'mapping-layout.json',
        ]
        for path in layouts:
            text = path.read_text()
            json.loads(text)
            self.assertIn('/camera/image_raw', text)
            self.assertNotIn('overhead', text.lower())


if __name__ == '__main__':
    unittest.main()
