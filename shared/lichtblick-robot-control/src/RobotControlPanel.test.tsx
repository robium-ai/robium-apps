import { JSDOM } from "jsdom";
import assert from "node:assert/strict";
import test from "node:test";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

import { RobotControlPanel, type ControlPanelAdapter } from "./RobotControlPanel";
import type { Direction } from "./messages";
import { DEFAULT_CONFIG } from "./panelConfig";

function renderPanel(mode: "MAPPING" | "LOCALIZATION" | "IDLE" | "UNKNOWN" = "MAPPING") {
  const dom = new JSDOM("<!doctype html><html><body><div id='root'></div></body></html>", {
    url: "http://localhost",
  });
  const previous = {
    window: globalThis.window,
    document: globalThis.document,
    HTMLElement: globalThis.HTMLElement,
    KeyboardEvent: globalThis.KeyboardEvent,
  };
  Object.assign(globalThis, {
    window: dom.window,
    document: dom.window.document,
    HTMLElement: dom.window.HTMLElement,
    KeyboardEvent: dom.window.KeyboardEvent,
    IS_REACT_ACT_ENVIRONMENT: true,
  });
  Object.assign(dom.window.HTMLElement.prototype, {
    attachEvent: () => undefined,
    detachEvent: () => undefined,
  });
  const movement: Array<["press" | "release" | "stop", Direction?]> = [];
  const actions: unknown[][] = [];
  const updates: Array<Record<string, number>> = [];
  let subscriber: (() => void) | undefined;
  const adapter = {
    snapshot: {
      config: DEFAULT_CONFIG,
      mode,
      maps: ["house", "office"],
      world: "house",
      colorScheme: "dark",
      canPublish: true,
      canCallServices: true,
      busy: false,
    },
    drive: {
      press: (direction) => movement.push(["press", direction]),
      release: (direction) => movement.push(["release", direction]),
      stop: () => movement.push(["stop"]),
    },
    subscribe: (listener) => {
      subscriber = listener;
      return () => {
        subscriber = undefined;
      };
    },
    runMapAction: async (...args) => {
      actions.push(args);
    },
    runSimulationAction: async (...args) => {
      actions.push(args);
    },
    callConfiguredService: async (...args) => {
      actions.push(args);
    },
    updateConfig: (patch: Record<string, number>) => updates.push(patch),
  } as ControlPanelAdapter & { updateConfig(patch: Record<string, number>): void };
  const rootElement = dom.window.document.querySelector("#root");
  assert.ok(rootElement);
  let root: Root;
  act(() => {
    root = createRoot(rootElement);
    root.render(<RobotControlPanel adapter={adapter} />);
  });
  return {
    dom,
    root: root!,
    adapter,
    movement,
    actions,
    updates,
    notify: () => subscriber?.(),
    cleanup: () => {
      act(() => root!.unmount());
      Object.assign(globalThis, previous);
      delete (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT;
    },
  };
}

test("updates movement speeds through persisted panel config", () => {
  const fixture = renderPanel();
  const forward = fixture.dom.window.document.querySelector<HTMLInputElement>(
    'input[aria-label="Forward speed"]',
  );
  const turn = fixture.dom.window.document.querySelector<HTMLInputElement>(
    'input[aria-label="Turn speed"]',
  );
  assert.ok(forward && turn);
  assert.deepEqual(
    { min: forward.min, max: forward.max, step: forward.step, value: forward.value },
    { min: "0.05", max: "0.5", step: "0.05", value: "0.2" },
  );
  assert.deepEqual(
    { min: turn.min, max: turn.max, step: turn.step, value: turn.value },
    { min: "0.1", max: "1.5", step: "0.1", value: "0.8" },
  );

  const valueSetter = Object.getOwnPropertyDescriptor(
    fixture.dom.window.HTMLInputElement.prototype,
    "value",
  )?.set;
  assert.ok(valueSetter);
  act(() => {
    valueSetter.call(forward, "0.35");
    forward.dispatchEvent(new fixture.dom.window.Event("input", { bubbles: true }));
  });
  assert.deepEqual(fixture.updates, [{ linearSpeed: 0.35 }]);
  fixture.cleanup();
});

test("renders accessible WASD, mapping, home, and stop controls", () => {
  const fixture = renderPanel();
  for (const label of [
    "Move forward",
    "Turn left",
    "Move backward",
    "Turn right",
    "Start mapping",
    "Stop mapping",
    "Load map",
    "Restart simulation",
    "Go home",
    "Stop robot",
  ]) {
    assert.ok(fixture.dom.window.document.querySelector(`[aria-label="${label}"]`), label);
  }
  const home =
    fixture.dom.window.document.querySelector<HTMLButtonElement>('[aria-label="Go home"]');
  assert.equal(home?.disabled, true);
  fixture.cleanup();
});

test("starts IDLE with a valid default map name and enabled mapping action", () => {
  const fixture = renderPanel("IDLE");
  const input = fixture.dom.window.document.querySelector<HTMLInputElement>("#map-name");
  const start = fixture.dom.window.document.querySelector<HTMLButtonElement>(
    '[aria-label="Start mapping"]',
  );
  assert.equal(input?.value, "map");
  assert.equal(start?.disabled, false);
  fixture.cleanup();
});

test("offers four simulation worlds and requests the selected restart", async () => {
  const fixture = renderPanel("IDLE");
  const select = fixture.dom.window.document.querySelector<HTMLSelectElement>("#simulation-world");
  const restart = fixture.dom.window.document.querySelector<HTMLButtonElement>(
    '[aria-label="Restart simulation"]',
  );
  assert.ok(select && restart);
  assert.deepEqual(
    [...select.options].map((option) => [option.value, option.text]),
    [
      ["house", "TurtleBot3 House"],
      ["tugbot_warehouse", "Tugbot in Warehouse"],
      ["industrial_warehouse", "Industrial Warehouse"],
      ["living_room", "Living Room"],
    ],
  );
  const valueSetter = Object.getOwnPropertyDescriptor(
    fixture.dom.window.HTMLSelectElement.prototype,
    "value",
  )?.set;
  assert.ok(valueSetter);
  act(() => {
    valueSetter.call(select, "living_room");
    select.dispatchEvent(new fixture.dom.window.Event("change", { bubbles: true }));
  });
  await act(async () => restart.click());
  assert.deepEqual(fixture.actions, [["living_room"]]);
  fixture.cleanup();
});

test("synchronizes the selected world after a simulator restart", () => {
  const fixture = renderPanel("IDLE");
  const select = fixture.dom.window.document.querySelector<HTMLSelectElement>("#simulation-world");
  assert.ok(select);
  assert.equal(select.value, "house");
  Object.assign(fixture.adapter, {
    snapshot: { ...fixture.adapter.snapshot, world: "living_room" },
  });
  act(() => fixture.notify());
  assert.equal(select.value, "living_room");
  fixture.cleanup();
});

test("removes secondary copy while preserving accessible controls", () => {
  const fixture = renderPanel();
  const document = fixture.dom.window.document;
  assert.equal(document.querySelectorAll(".eyebrow").length, 0);
  assert.equal(document.querySelectorAll(".drive-key small").length, 0);
  assert.equal(document.querySelectorAll(".speed-readout").length, 0);
  assert.equal(document.querySelectorAll(".connection-dot").length, 0);
  assert.equal(document.querySelectorAll(".hint").length, 0);
  for (const label of ["Move forward", "Turn left", "Move backward", "Turn right"]) {
    assert.ok(document.querySelector(`[aria-label="${label}"]`), label);
  }
  fixture.cleanup();
});

test("shows map options and gates load while the robot is mapping", () => {
  const fixture = renderPanel("MAPPING");
  const options = [...fixture.dom.window.document.querySelectorAll("#available-map option")].map(
    (option) => option.textContent,
  );
  assert.deepEqual(options, ["Select a map", "house", "office"]);
  const load =
    fixture.dom.window.document.querySelector<HTMLButtonElement>('[aria-label="Load map"]');
  const stopMapping = fixture.dom.window.document.querySelector<HTMLButtonElement>(
    '[aria-label="Stop mapping"]',
  );
  assert.equal(load?.disabled, true);
  assert.equal(stopMapping?.disabled, false);
  fixture.cleanup();
});

test("keeps movement shortcuts inactive while the map-name input owns focus", () => {
  const fixture = renderPanel();
  const input = fixture.dom.window.document.querySelector<HTMLInputElement>("#map-name");
  assert.ok(input);
  input.focus();
  fixture.dom.window.dispatchEvent(new fixture.dom.window.KeyboardEvent("keydown", { key: "w" }));
  assert.deepEqual(fixture.movement, []);
  input.blur();
  fixture.dom.window.dispatchEvent(new fixture.dom.window.KeyboardEvent("keydown", { key: "w" }));
  fixture.dom.window.dispatchEvent(new fixture.dom.window.KeyboardEvent("keyup", { key: "w" }));
  assert.deepEqual(fixture.movement.slice(-2), [
    ["press", "forward"],
    ["release", "forward"],
  ]);
  fixture.cleanup();
});

test("validates map names and sends the selected mapping action", async () => {
  const fixture = renderPanel("IDLE");
  const input = fixture.dom.window.document.querySelector<HTMLInputElement>("#map-name");
  const start = fixture.dom.window.document.querySelector<HTMLButtonElement>(
    '[aria-label="Start mapping"]',
  );
  assert.ok(input && start);
  const valueSetter = Object.getOwnPropertyDescriptor(
    fixture.dom.window.HTMLInputElement.prototype,
    "value",
  )?.set;
  assert.ok(valueSetter);
  act(() => {
    valueSetter.call(input, "../bad");
    input.dispatchEvent(new fixture.dom.window.Event("input", { bubbles: true }));
  });
  assert.equal(start.disabled, true);
  act(() => {
    valueSetter.call(input, "new_floor");
    input.dispatchEvent(new fixture.dom.window.Event("input", { bubbles: true }));
  });
  assert.equal(start.disabled, false);
  await act(async () => start.click());
  assert.deepEqual(fixture.actions, [["new_floor", "startMappingService"]]);
  fixture.cleanup();
});
