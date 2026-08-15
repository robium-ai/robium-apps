import type { PanelExtensionContext, RenderState } from "@lichtblick/suite";
import assert from "node:assert/strict";
import test from "node:test";

import { LichtblickAdapter } from "./lichtblickAdapter";
import { DEFAULT_CONFIG } from "./panelConfig";

type Calls = {
  watched: string[];
  subscriptions: unknown[][];
  advertised: unknown[][];
  unadvertised: string[];
  published: unknown[][];
  parameters: unknown[][];
  services: Array<{ service: string; request: unknown }>;
  saved: unknown[];
  done: number;
};

function makePanelContext() {
  const calls: Calls = {
    watched: [],
    subscriptions: [],
    advertised: [],
    unadvertised: [],
    published: [],
    parameters: [],
    services: [],
    saved: [],
    done: 0,
  };
  const context = {
    initialState: {},
    panelElement: {} as HTMLDivElement,
    watch: (field: string) => calls.watched.push(field),
    subscribe: (subscriptions: unknown[]) => calls.subscriptions.push(subscriptions),
    unsubscribeAll: () => calls.subscriptions.push([]),
    advertise: (...args: unknown[]) => calls.advertised.push(args),
    unadvertise: (topic: string) => calls.unadvertised.push(topic),
    publish: (...args: unknown[]) => calls.published.push(args),
    setParameter: (...args: unknown[]) => calls.parameters.push(args),
    callService: async (service: string, request: unknown) => {
      calls.services.push({ service, request });
      return {};
    },
    saveState: (state: unknown) => calls.saved.push(state),
    updatePanelSettingsEditor: () => undefined,
    setDefaultPanelTitle: () => undefined,
  } as unknown as PanelExtensionContext;
  return {
    context,
    calls,
    render: (state: Partial<RenderState>) =>
      context.onRender?.(state, () => {
        calls.done += 1;
      }),
  };
}

test("subscribes, watches exact render fields, and acknowledges every render", () => {
  const fixture = makePanelContext();
  const adapter = new LichtblickAdapter(fixture.context, DEFAULT_CONFIG);
  assert.deepEqual(fixture.calls.watched, ["currentFrame", "parameters", "colorScheme"]);
  assert.deepEqual(fixture.calls.subscriptions[0], [
    { topic: "/mapping/state" },
    { topic: "/maps/available" },
    { topic: "/simulation/state" },
    { topic: "/waypoints/available" },
  ]);
  fixture.render({
    currentFrame: [
      { topic: "/mapping/state", message: { data: "MAPPING" } },
      { topic: "/maps/available", message: { data: "office\nhouse" } },
      { topic: "/waypoints/available", message: { data: "Lobby\nKitchen" } },
    ] as never,
    colorScheme: "dark",
  });
  assert.equal(fixture.calls.done, 1);
  assert.equal(adapter.snapshot.mode, "MAPPING");
  assert.deepEqual(adapter.snapshot.maps, ["house", "office"]);
  assert.deepEqual(adapter.snapshot.waypoints, ["Kitchen", "Lobby"]);
  assert.equal(adapter.snapshot.colorScheme, "dark");
  adapter.dispose();
});

test("waits for the selected simulation world before requesting restart", async () => {
  const fixture = makePanelContext();
  const adapter = new LichtblickAdapter(fixture.context, DEFAULT_CONFIG);
  const action = adapter.runSimulationAction("furnished_house");
  assert.deepEqual(fixture.calls.parameters, [["/session_manager.world", "furnished_house"]]);
  assert.deepEqual(fixture.calls.services, []);
  fixture.render({
    parameters: new Map([["/session_manager.world", "furnished_house"]]),
  });
  await action;
  assert.deepEqual(fixture.calls.services, [{ service: "/simulation/restart", request: {} }]);
  adapter.dispose();
});

test("advertises Twist before publishing and cleans up", () => {
  const fixture = makePanelContext();
  const adapter = new LichtblickAdapter(fixture.context, DEFAULT_CONFIG);
  assert.deepEqual(fixture.calls.advertised[0], ["/cmd_vel_teleop", "geometry_msgs/msg/Twist"]);
  adapter.drive.press("forward");
  assert.equal(fixture.calls.published[0]?.[0], "/cmd_vel_teleop");
  adapter.dispose();
  assert.deepEqual(fixture.calls.unadvertised, ["/cmd_vel_teleop"]);
  assert.deepEqual(fixture.calls.subscriptions.at(-1), []);
});

test("waits for the selected map parameter before calling the service", async () => {
  const fixture = makePanelContext();
  const adapter = new LichtblickAdapter(fixture.context, DEFAULT_CONFIG);
  const action = adapter.runMapAction("house", "stopMappingService");
  assert.deepEqual(fixture.calls.parameters, [["/session_manager.map_name", "house"]]);
  assert.deepEqual(fixture.calls.services, []);
  fixture.render({ parameters: new Map([["/session_manager.map_name", "house"]]) });
  await action;
  assert.deepEqual(fixture.calls.services, [{ service: "/mapping/stop", request: {} }]);
  adapter.dispose();
});

test("waits for the selected waypoint before requesting navigation", async () => {
  const fixture = makePanelContext();
  const adapter = new LichtblickAdapter(fixture.context, DEFAULT_CONFIG);
  const action = adapter.runWaypointAction("Kitchen", "navigateWaypointService");
  assert.deepEqual(fixture.calls.parameters, [
    ["/session_manager.waypoint_name", "Kitchen"],
  ]);
  assert.deepEqual(fixture.calls.services, []);
  fixture.render({
    parameters: new Map([["/session_manager.waypoint_name", "Kitchen"]]),
  });
  await action;
  assert.deepEqual(fixture.calls.services, [
    { service: "/waypoints/navigate", request: {} },
  ]);
  assert.equal(adapter.snapshot.status?.message, "Navigation request sent for Kitchen.");
  adapter.dispose();
});

test("rejects invalid waypoint names before changing a parameter", async () => {
  const fixture = makePanelContext();
  const adapter = new LichtblickAdapter(fixture.context, DEFAULT_CONFIG);
  await assert.rejects(
    adapter.runWaypointAction("../escape", "saveWaypointService"),
    /valid waypoint name/i,
  );
  assert.deepEqual(fixture.calls.parameters, []);
  assert.deepEqual(fixture.calls.services, []);
  adapter.dispose();
});

test("surfaces a waypoint Trigger refusal", async () => {
  const fixture = makePanelContext();
  fixture.context.callService = async () => ({
    success: false,
    message: "waypoint actions require an active LOCALIZATION session",
  });
  const adapter = new LichtblickAdapter(fixture.context, DEFAULT_CONFIG);
  const action = adapter.runWaypointAction("Kitchen", "deleteWaypointService");
  fixture.render({
    parameters: new Map([["/session_manager.waypoint_name", "Kitchen"]]),
  });
  await assert.rejects(action, /LOCALIZATION/);
  assert.equal(adapter.snapshot.status?.kind, "error");
  adapter.dispose();
});

test("rejects a map action when parameter acknowledgement times out", async () => {
  const fixture = makePanelContext();
  const adapter = new LichtblickAdapter(fixture.context, DEFAULT_CONFIG, { parameterTimeoutMs: 5 });
  await assert.rejects(
    adapter.runMapAction("house", "loadMapService"),
    /parameter acknowledgement/i,
  );
  assert.deepEqual(fixture.calls.services, []);
  adapter.dispose();
});

test("surfaces a Trigger response that refuses an invalid state transition", async () => {
  const fixture = makePanelContext();
  fixture.context.callService = async () => ({
    success: false,
    message: "stop mapping requires an active mapping session",
  });
  const adapter = new LichtblickAdapter(fixture.context, DEFAULT_CONFIG);
  const action = adapter.runMapAction("house", "stopMappingService");
  fixture.render({ parameters: new Map([["/session_manager.map_name", "house"]]) });
  await assert.rejects(action, /requires an active mapping session/);
  assert.equal(adapter.snapshot.status?.kind, "error");
  adapter.dispose();
});

test("surfaces service rejection and persists normalized settings", async () => {
  const fixture = makePanelContext();
  fixture.context.callService = async () => {
    throw new Error("service unavailable");
  };
  const adapter = new LichtblickAdapter(fixture.context, DEFAULT_CONFIG);
  const action = adapter.runMapAction("house", "startMappingService");
  fixture.render({ parameters: new Map([["/session_manager.map_name", "house"]]) });
  await assert.rejects(action, /service unavailable/);
  adapter.updateConfig({ teleopTopic: "/robot/cmd_vel" });
  assert.equal(
    (fixture.calls.saved.at(-1) as { teleopTopic: string }).teleopTopic,
    "/robot/cmd_vel",
  );
  assert.deepEqual(fixture.calls.unadvertised, ["/cmd_vel_teleop"]);
  adapter.dispose();
});
