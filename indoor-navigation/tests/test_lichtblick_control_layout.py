import json
import unittest
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
LAYOUT_PATH = APP_ROOT / "lichtblick" / "mapping-layout.json"


class LichtblickControlLayoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.layout = json.loads(LAYOUT_PATH.read_text(encoding="utf-8"))

    def test_control_panel_is_docked_in_a_76_24_right_rail(self):
        root = self.layout["layout"]
        self.assertEqual(root["direction"], "row")
        self.assertEqual(root["splitPercentage"], 76)
        self.assertEqual(root["second"], "Robium Robot Control.robot-control!control")

        main = root["first"]
        self.assertEqual(main["direction"], "column")
        self.assertEqual(main["first"], "3D!dash")
        self.assertEqual(main["second"], "Image!robotcam")
        self.assertEqual(main["splitPercentage"], 78)

    def test_replaces_fragmented_builtin_controls(self):
        config_ids = set(self.layout["configById"])
        old_prefixes = ("Teleop!", "CallService!", "Indicator!", "Parameters!", "RawMessages!")
        self.assertFalse(any(panel.startswith(old_prefixes) for panel in config_ids))

    def test_custom_panel_state_matches_shared_extension_defaults(self):
        state = self.layout["configById"]["Robium Robot Control.robot-control!control"]
        self.assertEqual(
            state,
            {
                "version": 1,
                "teleopTopic": "/cmd_vel_teleop",
                "mappingStateTopic": "/mapping/state",
                "availableMapsTopic": "/maps/available",
                "simulationStateTopic": "/simulation/state",
                "mapNameParameter": "/session_manager.map_name",
                "worldParameter": "/session_manager.world",
                "startMappingService": "/mapping/start",
                "stopMappingService": "/mapping/stop",
                "loadMapService": "/mapping/load",
                "restartSimulationService": "/simulation/restart",
                "goHomeService": "",
                "navigationStopService": "",
                "linearSpeed": 0.2,
                "angularSpeed": 0.8,
                "publishRateHz": 10,
            },
        )


if __name__ == "__main__":
    unittest.main()
