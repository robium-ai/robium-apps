# Lichtblick Robot Control Extension Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a reusable `.foxe` Robot Control panel and integrate it as indoor-navigation's right-side mapping control rail.

**Architecture:** A shared TypeScript/React extension contains pure configuration, map parsing, drive-state, and adapter logic around `PanelExtensionContext`; indoor-navigation supplies ROS defaults through layout state. The existing `teleop_relay` and `map_manager` remain the robot-side boundary.

**Tech Stack:** TypeScript, React 18, `@lichtblick/suite`, `create-lichtblick-extension`, Node's test runner through `tsx`, Python `unittest`, Docker/ROS 2 Jazzy live smoke.

## Global Constraints

- Package identity stays `robot-control` / publisher `robium` / display name `Robium Robot Control`; registered panel name stays `robot-control`.
- Default teleop is `/cmd_vel_teleop`, `geometry_msgs/msg/Twist`, linear `0.2`, angular `0.8`, 10 Hz.
- Map names match `^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$`.
- Map actions set `/map_manager.map_name`, wait at most three seconds for render-state acknowledgement, then call the configured service.
- Load never claims to switch a mapping graph into localization.
- Stop is a motion-command stop, not an emergency stop.
- No generated `dist/`, `node_modules/`, or `.foxe` artifact is committed.
- Follow TDD: each production behavior begins with a test that fails for the intended missing behavior.

---

### Task 1: Scaffold the extension around tested pure behavior

**Files:**
- Create: `shared/lichtblick-robot-control/package.json`
- Create: `shared/lichtblick-robot-control/package-lock.json`
- Create: `shared/lichtblick-robot-control/tsconfig.json`
- Create: `shared/lichtblick-robot-control/.eslintrc.yaml`
- Create: `shared/lichtblick-robot-control/.prettierrc.yaml`
- Create: `shared/lichtblick-robot-control/.gitignore`
- Create: `shared/lichtblick-robot-control/config.ts`
- Test: `shared/lichtblick-robot-control/src/panelConfig.test.ts`
- Create: `shared/lichtblick-robot-control/src/panelConfig.ts`
- Test: `shared/lichtblick-robot-control/src/driveController.test.ts`
- Create: `shared/lichtblick-robot-control/src/driveController.ts`
- Create: `shared/lichtblick-robot-control/src/messages.ts`

**Interfaces:**
- Produces: `PanelConfig`, `DEFAULT_CONFIG`, `normalizeConfig`, `validateMapName`, `parseAvailableMaps`.
- Produces: `DriveController.press(direction)`, `release(direction)`, `stop()`, `dispose()`, with injected `publish(Twist)` and timer functions.

- [ ] **Step 1: Add the official package configuration and install a locked toolchain**

Use the official generator versions already inspected: `create-lichtblick-extension@1.1.0`, `@lichtblick/suite@1.8.0`, React 18.3.1, TypeScript 5.7.2. Add `tsx`, `jsdom`, and `@types/jsdom` for Node-native TypeScript and DOM tests. Scripts are `test: tsx --test src/*.test.ts src/*.test.tsx`, `build`, `lint`, `package`, and `local-install`.

The core interfaces are fixed before tests:

```ts
export type Direction = "forward" | "backward" | "left" | "right";
export type Twist = {
  linear: { x: number; y: number; z: number };
  angular: { x: number; y: number; z: number };
};

export type PanelConfig = {
  version: 1;
  teleopTopic: string;
  mappingStateTopic: string;
  availableMapsTopic: string;
  mapNameParameter: string;
  startMappingService: string;
  stopMappingService: string;
  loadMapService: string;
  goHomeService: string;
  navigationStopService: string;
  linearSpeed: number;
  angularSpeed: number;
  publishRateHz: number;
};
```

- [ ] **Step 2: Write failing config/map tests**

Cover literal defaults, partial-state normalization, strict map-name validation, newline parsing, sentinel removal, deduplication, and sorting.

```ts
test("rejects map names that can escape the maps directory", () => {
  assert.equal(validateMapName("../house"), false);
  assert.equal(validateMapName("house/level1"), false);
  assert.equal(validateMapName("house_level-1"), true);
});
```

- [ ] **Step 3: Run the config tests and confirm they fail because exports are missing**

Run: `npm test -- panelConfig.test.ts`

- [ ] **Step 4: Implement the minimal config/map functions and make the tests pass**

- [ ] **Step 5: Write failing drive-controller tests**

Tests must prove W/S and A/D axis signs, opposite-key cancellation, diagonals, 10 Hz repetition under fake timers, zero on final release, and zero plus timer cleanup on disposal.

```ts
test("publishes zero when the final held direction is released", () => {
  const published: Twist[] = [];
  const drive = new DriveController({ config: DEFAULT_CONFIG, publish: (msg) => published.push(msg) });
  drive.press("forward");
  drive.release("forward");
  assert.deepEqual(published.at(-1), ZERO_TWIST);
});
```

- [ ] **Step 6: Run the drive tests and confirm they fail because DriveController is missing**

- [ ] **Step 7: Implement DriveController and make all Task 1 tests pass**

- [ ] **Step 8: Commit Task 1**

```bash
git add shared/lichtblick-robot-control
git commit -m "feat(shared): scaffold tested Lichtblick robot controls"
```

### Task 2: Build the Lichtblick adapter and control panel

**Files:**
- Test: `shared/lichtblick-robot-control/src/lichtblickAdapter.test.ts`
- Create: `shared/lichtblick-robot-control/src/lichtblickAdapter.ts`
- Test: `shared/lichtblick-robot-control/src/RobotControlPanel.test.tsx`
- Create: `shared/lichtblick-robot-control/src/RobotControlPanel.tsx`
- Create: `shared/lichtblick-robot-control/src/styles.css`
- Create: `shared/lichtblick-robot-control/src/index.ts`

**Interfaces:**
- Consumes: Task 1 config, parsing, Twist builder, and `DriveController`.
- Produces: `LichtblickAdapter` snapshots containing topics, mode, maps, parameter values, color scheme, capability flags, and action results.
- Produces: `initRobotControlPanel(context): () => void` and extension `activate(context)`.

- [ ] **Step 1: Write failing adapter tests with a complete fake PanelExtensionContext boundary**

Prove topic subscription, exact watched fields, `done()` once per render, state/map parsing, publish advertise/unadvertise, map-name acknowledgement before service call, three-second timeout, call rejection, state persistence, and cleanup.

```ts
test("waits for the selected map parameter before calling the service", async () => {
  const context = makePanelContext();
  const adapter = new LichtblickAdapter(context, DEFAULT_CONFIG);
  const action = adapter.runMapAction("house", "stopMappingService");
  assert.deepEqual(context.calls.services, []);
  context.render({ parameters: new Map([["/map_manager.map_name", "house"]]) });
  await action;
  assert.deepEqual(context.calls.services, [{ service: "/mapping/save", request: {} }]);
});
```

- [ ] **Step 2: Run adapter tests and confirm the adapter is missing**

- [ ] **Step 3: Implement the adapter and make its tests pass**

- [ ] **Step 4: Write failing panel tests**

Render against jsdom and assert real accessible controls: WASD buttons, map-name validation, map options, correct mode gating, Home disabled when unconfigured, Stop always present, and keyboard input ignored from form elements.

```tsx
test("keeps movement shortcuts inactive while the map-name input owns focus", () => {
  const fixture = renderPanel({ mode: "MAPPING" });
  fixture.mapNameInput.focus();
  fixture.window.dispatchEvent(new KeyboardEvent("keydown", { key: "w" }));
  assert.deepEqual(fixture.published, []);
});
```

- [ ] **Step 5: Run panel tests and confirm the panel is missing**

- [ ] **Step 6: Implement the React panel, styles, keyboard/pointer cleanup, settings-editor configuration, and entry point**

- [ ] **Step 7: Run test, lint, build, and package**

```bash
npm test
npm run lint
npm run build
npm run package
```

- [ ] **Step 8: Inspect the `.foxe` archive for `package.json` and its declared compiled entry**

- [ ] **Step 9: Commit Task 2**

```bash
git add shared/lichtblick-robot-control
git commit -m "feat(shared): add reusable Lichtblick robot control panel"
```

### Task 3: Integrate the panel into indoor-navigation

**Files:**
- Test: `indoor-navigation/tests/test_lichtblick_control_layout.py`
- Modify: `indoor-navigation/lichtblick/mapping-layout.json`
- Modify: `indoor-navigation/Makefile`

**Interfaces:**
- Consumes: panel type `Robium Robot Control.robot-control` and Task 1 default state.
- Produces: a 72/28 top-level split with 3D+camera left and control panel right; `make control-extension` packages the `.foxe`.

- [ ] **Step 1: Write a failing layout test**

Load real JSON and assert the right branch panel type, 72% left split, 78/22 3D/camera left column, removal of the old fragmented built-in control panels, and config values matching the shared package defaults.

- [ ] **Step 2: Run the layout test and confirm it fails against the old layout**

- [ ] **Step 3: Replace the old control mosaic with the custom-panel layout**

- [ ] **Step 4: Add `control-extension` and `control-extension-check` Make targets**

The targets run `npm ci`, tests/lint/build/package, then print the exact `.foxe` path.

- [ ] **Step 5: Keep the extension outside the Docker image for the one-time browser install flow**

No Dockerfile source rebuild is required; the generated `.foxe` remains a host-side artifact for drag/open installation.

- [ ] **Step 6: Run layout and existing dependency-free app tests**

- [ ] **Step 7: Commit Task 3**

```bash
git add indoor-navigation
git commit -m "feat(indoor-navigation): dock reusable Lichtblick controls"
```

### Task 4: Document, verify, and smoke the real integration

**Files:**
- Create: `shared/lichtblick-robot-control/README.md`
- Create: `shared/lichtblick-robot-control/LICENSE`
- Create: `shared/lichtblick-robot-control/CHANGELOG.md`
- Modify: `indoor-navigation/README.md`
- Modify: `indoor-navigation/docs/architecture-brief.md`
- Modify: `REGISTRY.md`
- Modify: `learnings/2026-08-12-indoor-navigation.md` in the sibling robium repo as events occur

**Interfaces:**
- Produces: build/install/reuse instructions, current limitation documentation, registry verification date, and smoke evidence.

- [ ] **Step 1: Document build/package, drag/open installation, config fields, safety semantics, and reuse**

- [ ] **Step 2: Run the complete extension gate**

```bash
make control-extension-check
```

- [ ] **Step 3: Run all host-side tests available in the correct app environment**

- [ ] **Step 4: Start the real mapping stack and bundled viewer**

```bash
make mapping
```

- [ ] **Step 5: Install the generated `.foxe`, open the committed layout, and verify live state, map list, W motion, and zero/deadman stop**

- [ ] **Step 6: Run a disposable map action and verify parameter acknowledgement precedes the service**

- [ ] **Step 7: Update `REGISTRY.md` verified date only after the smoke pass**

- [ ] **Step 8: Run final diff checks and the relevant existing app smoke gate**

- [ ] **Step 9: Commit Task 4**

```bash
git add shared/lichtblick-robot-control indoor-navigation REGISTRY.md
git commit -m "docs(indoor-navigation): document Lichtblick control extension"
```
