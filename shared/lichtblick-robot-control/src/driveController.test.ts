import assert from "node:assert/strict";
import test from "node:test";

import { DriveController } from "./driveController";
import { DEFAULT_CONFIG } from "./panelConfig";
import { ZERO_TWIST, type Twist } from "./messages";

function fixture() {
  const published: Twist[] = [];
  let interval: (() => void) | undefined;
  let delay: number | undefined;
  let cleared = false;
  const drive = new DriveController({
    config: DEFAULT_CONFIG,
    publish: (message) => published.push(message),
    setInterval: (callback, intervalMs) => {
      interval = callback;
      delay = intervalMs;
      return 42;
    },
    clearInterval: (id) => {
      assert.equal(id, 42);
      cleared = true;
    },
  });
  return { drive, published, tick: () => interval?.(), delay: () => delay, cleared: () => cleared };
}

test("maps W/S and A/D directions to ROS Twist axes", () => {
  const { drive, published } = fixture();
  drive.press("forward");
  assert.equal(published.at(-1)?.linear.x, 0.2);
  drive.release("forward");
  drive.press("backward");
  assert.equal(published.at(-1)?.linear.x, -0.2);
  drive.release("backward");
  drive.press("left");
  assert.equal(published.at(-1)?.angular.z, 0.8);
  drive.release("left");
  drive.press("right");
  assert.equal(published.at(-1)?.angular.z, -0.8);
});

test("supports diagonals and cancels opposite held keys", () => {
  const { drive, published } = fixture();
  drive.press("forward");
  drive.press("left");
  assert.deepEqual(published.at(-1), {
    linear: { x: 0.2, y: 0, z: 0 },
    angular: { x: 0, y: 0, z: 0.8 },
  });
  drive.press("backward");
  assert.equal(published.at(-1)?.linear.x, 0);
  assert.equal(published.at(-1)?.angular.z, 0.8);
});

test("repeats held commands at the configured 10 Hz", () => {
  const { drive, published, tick, delay } = fixture();
  drive.press("forward");
  assert.equal(delay(), 100);
  tick();
  assert.equal(published.length, 2);
  assert.equal(published.at(-1)?.linear.x, 0.2);
});

test("publishes zero when the final held direction is released", () => {
  const { drive, published, cleared } = fixture();
  drive.press("forward");
  drive.release("forward");
  assert.deepEqual(published.at(-1), ZERO_TWIST);
  assert.equal(cleared(), true);
});

test("stop and dispose publish zero and clear held state", () => {
  const { drive, published, tick, cleared } = fixture();
  drive.press("forward");
  drive.stop();
  assert.deepEqual(published.at(-1), ZERO_TWIST);
  assert.equal(cleared(), true);
  const count = published.length;
  tick();
  assert.equal(published.length, count + 1, "stale test callback can only publish zero");
  assert.deepEqual(published.at(-1), ZERO_TWIST);
  drive.dispose();
  assert.deepEqual(published.at(-1), ZERO_TWIST);
});
