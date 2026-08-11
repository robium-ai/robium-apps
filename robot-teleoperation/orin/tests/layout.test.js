import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const path = fileURLToPath(new URL('../../foxglove/tb4-teleop-layout.json', import.meta.url));

test('phase-1 layout is valid JSON and still has a Teleop panel on /cmd_vel', () => {
  const layout = JSON.parse(readFileSync(path, 'utf8'));
  const cfg = layout.configById || {};
  const teleopKey = Object.keys(cfg).find((k) => k.startsWith('Teleop!'));
  assert.ok(teleopKey, 'no Teleop panel in layout');
  assert.equal(cfg[teleopKey].topic, '/cmd_vel');
});
