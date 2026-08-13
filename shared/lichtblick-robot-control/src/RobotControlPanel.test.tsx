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
  const adapter: ControlPanelAdapter = {
    snapshot: {
      config: DEFAULT_CONFIG,
      mode,
      maps: ["house", "office"],
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
    subscribe: () => () => undefined,
    runMapAction: async (...args) => {
      actions.push(args);
    },
    callConfiguredService: async (...args) => {
      actions.push(args);
    },
  };
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
    cleanup: () => {
      act(() => root!.unmount());
      Object.assign(globalThis, previous);
      delete (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT;
    },
  };
}

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

test("shows map options and gates load while the robot is mapping", () => {
  const fixture = renderPanel("MAPPING");
  const options = [...fixture.dom.window.document.querySelectorAll("option")].map(
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
