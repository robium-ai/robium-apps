import assert from "node:assert/strict";
import test from "node:test";

import {
  DEFAULT_CONFIG,
  normalizeConfig,
  parseAvailableMaps,
  validateMapName,
} from "./panelConfig";

test("uses the indoor-navigation ROS interfaces by default", () => {
  assert.equal(DEFAULT_CONFIG.teleopTopic, "/cmd_vel_teleop");
  assert.equal(DEFAULT_CONFIG.mappingStateTopic, "/mapping/state");
  assert.equal(DEFAULT_CONFIG.availableMapsTopic, "/maps/available");
  assert.equal(DEFAULT_CONFIG.mapNameParameter, "/map_manager.map_name");
  assert.equal(DEFAULT_CONFIG.startMappingService, "/mapping/reset");
  assert.equal(DEFAULT_CONFIG.stopMappingService, "/mapping/save");
  assert.equal(DEFAULT_CONFIG.loadMapService, "/mapping/load");
  assert.equal(DEFAULT_CONFIG.linearSpeed, 0.2);
  assert.equal(DEFAULT_CONFIG.angularSpeed, 0.8);
  assert.equal(DEFAULT_CONFIG.publishRateHz, 10);
});

test("normalizes partial and stale panel state", () => {
  assert.deepEqual(normalizeConfig({ teleopTopic: "/base/cmd_vel", linearSpeed: -2 }), {
    ...DEFAULT_CONFIG,
    teleopTopic: "/base/cmd_vel",
    linearSpeed: DEFAULT_CONFIG.linearSpeed,
  });
  assert.deepEqual(normalizeConfig(undefined), DEFAULT_CONFIG);
});

test("rejects map names that can escape the maps directory", () => {
  assert.equal(validateMapName("../house"), false);
  assert.equal(validateMapName("house/level1"), false);
  assert.equal(validateMapName("house_level-1"), true);
  assert.equal(validateMapName(""), false);
  assert.equal(validateMapName(`a${"b".repeat(64)}`), false);
});

test("parses, validates, deduplicates, and sorts available maps", () => {
  assert.deepEqual(
    parseAvailableMaps("zeta\nnone\nhouse\nhouse\n../escape\nalpha\n"),
    ["alpha", "house", "zeta"],
  );
  assert.deepEqual(parseAvailableMaps({ data: "office, lobby;warehouse" }), [
    "lobby",
    "office",
    "warehouse",
  ]);
});
