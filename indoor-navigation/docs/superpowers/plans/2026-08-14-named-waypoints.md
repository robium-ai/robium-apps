# Named Waypoints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture the localized robot's current pose as a named, per-map waypoint and let Robot Control list, navigate to, and delete those waypoints.

**Architecture:** A ROS-independent Python store persists atomic per-map JSON sidecars. The existing session manager owns TF lookup, active-map gating, goal publication, Trigger services, and the latched waypoint-name topic; the shared Lichtblick extension calls those configurable interfaces through its existing acknowledged-parameter pattern.

**Tech Stack:** Python 3, ROS 2 Jazzy (`rclpy`, `tf2_ros`, `geometry_msgs`, `std_msgs`, `std_srvs`), TypeScript 5, React 18, Lichtblick extension SDK, `unittest`, Node test runner.

## Global Constraints

- Save captures the current `map -> base_footprint` transform; it never captures a clicked 3D-map pose.
- Save, navigate, and delete operate only in `LOCALIZATION` with an active map.
- Waypoints are scoped to `<maps-root>/<world>/<map>.waypoints.json` and duplicate names are rejected.
- Existing untracked saved-map directories are never modified, deleted, staged, or committed by tests or implementation work.
- A successful Navigate response means a goal was published, not that the robot reached it.
- Do not implement waypoint editing, renaming, sequences, patrols, or Lichtblick publish-toolbar changes.

---

### Task 1: Persist validated per-map waypoint sidecars

**Files:**
- Create: `indoor-navigation/src/indoor_nav_bringup/indoor_nav_bringup/waypoints.py`
- Create: `indoor-navigation/tests/test_waypoints.py`

**Interfaces:**
- Consumes: a temporary or runtime maps-root `Path`, world name, map name, and waypoint name.
- Produces: immutable `Waypoint(x: float, y: float, yaw: float)` and `WaypointStore.list_names`, `save`, `get`, and `delete` methods.

- [ ] **Step 1: Write failing store tests**

Create temporary-directory tests that require this API:

```python
store = WaypointStore(Path(tmp))
store.save('furnished_house', 'office', 'Kitchen', Waypoint(1.0, 2.0, 0.5))
self.assertEqual(store.list_names('furnished_house', 'office'), ['Kitchen'])
self.assertEqual(store.get('furnished_house', 'office', 'Kitchen'), Waypoint(1.0, 2.0, 0.5))
with self.assertRaisesRegex(ValueError, 'already exists'):
    store.save('furnished_house', 'office', 'Kitchen', Waypoint(9.0, 9.0, 0.0))
store.delete('furnished_house', 'office', 'Kitchen')
self.assertEqual(store.list_names('furnished_house', 'office'), [])
```

Also prove alphabetical listing, different-map isolation, unsafe-name rejection, non-finite pose rejection, missing waypoint errors, malformed JSON refusal without overwrite, and a document shaped as `{"version": 1, "waypoints": {"Kitchen": {"x": 1.0, "y": 2.0, "yaw": 0.5}}}`.

- [ ] **Step 2: Run the store tests and verify RED**

Run: `python3 -m unittest indoor-navigation/tests/test_waypoints.py -v`

Expected: import failure because `indoor_nav_bringup.waypoints` does not exist.

- [ ] **Step 3: Implement the minimal store**

Use a frozen dataclass and an atomic sibling write:

```python
@dataclass(frozen=True)
class Waypoint:
    x: float
    y: float
    yaw: float

class WaypointStore:
    def list_names(self, world, map_name): ...
    def save(self, world, map_name, name, waypoint): ...
    def get(self, world, map_name, name): ...
    def delete(self, world, map_name, name): ...

    def _path(self, world, map_name):
        return self._maps_root / world / f'{map_name}.waypoints.json'
```

Validate every path token with the existing 1–64 character rule, validate all coordinates with `math.isfinite`, reject unknown document keys/types, write `<map>.waypoints.json.tmp`, then call `os.replace`. Deleting the final waypoint removes the sidecar through `Path.unlink`; tests only exercise temporary roots.

- [ ] **Step 4: Run the store tests and verify GREEN**

Run: `python3 -m unittest indoor-navigation/tests/test_waypoints.py -v`

Expected: all waypoint-store tests pass.

- [ ] **Step 5: Commit the store**

```bash
git add indoor-navigation/src/indoor_nav_bringup/indoor_nav_bringup/waypoints.py indoor-navigation/tests/test_waypoints.py
git commit -m "feat(indoor-navigation): persist named waypoints"
```

---

### Task 2: Expose waypoint operations through the session manager

**Files:**
- Modify: `indoor-navigation/src/indoor_nav_bringup/indoor_nav_bringup/session_processes.py`
- Modify: `indoor-navigation/src/indoor_nav_bringup/indoor_nav_bringup/session_manager.py`
- Modify: `indoor-navigation/src/indoor_nav_bringup/package.xml`
- Modify: `indoor-navigation/tests/test_session_processes.py`
- Modify: `indoor-navigation/tests/test_waypoints.py`

**Interfaces:**
- Consumes: `WaypointStore`, current `SessionProcesses.mode/world/active_map`, an injected pose lookup, and injected goal publisher.
- Produces: `WaypointController.names()`, `save(name)`, `navigate(name)`, and `delete(name)`; ROS parameter `/session_manager.waypoint_name`; topic `/waypoints/available`; services `/waypoints/save`, `/waypoints/navigate`, `/waypoints/delete`; goal topic `/goal_pose`.

- [ ] **Step 1: Write failing session/controller tests**

Extend `SessionProcesses` tests to require `active_map is None` in IDLE, the selected name in MAPPING/LOCALIZATION, and `None` after stop/restart.

Add controller tests with injected callables:

```python
controller = WaypointController(
    store,
    context=lambda: ('LOCALIZATION', 'furnished_house', 'office'),
    lookup_pose=lambda: Waypoint(1.0, 2.0, 0.5),
    publish_goal=published.append,
)
self.assertIn('saved waypoint', controller.save('Kitchen'))
self.assertEqual(controller.names(), ['Kitchen'])
self.assertIn('navigation requested', controller.navigate('Kitchen'))
self.assertEqual(published, [Waypoint(1.0, 2.0, 0.5)])
```

Require all three actions to refuse `IDLE` and `MAPPING`, Save to propagate missing-TF errors without creating a file, and Delete/Navigate to reject unknown names.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `python3 -m unittest indoor-navigation/tests/test_session_processes.py indoor-navigation/tests/test_waypoints.py -v`

Expected: failures for missing `active_map` and `WaypointController`.

- [ ] **Step 3: Implement the controller and session state API**

Add:

```python
@property
def active_map(self):
    return self._map_name
```

Implement `WaypointController` in `waypoints.py`. Its `_scope()` must require mode `LOCALIZATION` and a non-empty active map before any list mutation or action. Save calls `lookup_pose()` before `store.save`; Navigate loads then calls `publish_goal(waypoint)`; Delete removes one entry.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run: `python3 -m unittest indoor-navigation/tests/test_session_processes.py indoor-navigation/tests/test_waypoints.py -v`

Expected: all focused tests pass.

- [ ] **Step 5: Integrate the ROS boundary**

In `SessionManager`:

```python
self.declare_parameter('waypoint_name', 'waypoint')
self._waypoint_pub = self.create_publisher(String, '/waypoints/available', LATCHED)
self._goal_pub = self.create_publisher(PoseStamped, '/goal_pose', 10)
self._tf_buffer = Buffer()
self._tf_listener = TransformListener(self._tf_buffer, self)
```

Create the three Trigger services. Service callbacks call `_result` with the controller operation and republish state. `_lookup_pose` calls `lookup_transform('map', 'base_footprint', Time())`, converts quaternion to yaw with `atan2`, and returns `Waypoint`. `_publish_goal` emits a stamped map-frame `PoseStamped` with a yaw-only quaternion. `publish_state` emits newline-separated waypoint names, or an empty string outside localization. Add explicit `package.xml` runtime dependencies for `rclpy`, `geometry_msgs`, and `tf2_ros`.

- [ ] **Step 6: Run focused Python tests and syntax checks**

Run:

```bash
python3 -m unittest indoor-navigation/tests/test_session_processes.py indoor-navigation/tests/test_waypoints.py -v
python3 -m py_compile indoor-navigation/src/indoor_nav_bringup/indoor_nav_bringup/session_manager.py indoor-navigation/src/indoor_nav_bringup/indoor_nav_bringup/waypoints.py
```

Expected: focused tests and syntax checks pass without reading or writing the real saved-map sidecars. The ROS-dependent full suite runs in the rebuilt app image in Task 4.

- [ ] **Step 7: Commit the ROS boundary**

```bash
git add indoor-navigation/src/indoor_nav_bringup/indoor_nav_bringup/session_processes.py indoor-navigation/src/indoor_nav_bringup/indoor_nav_bringup/session_manager.py indoor-navigation/src/indoor_nav_bringup/indoor_nav_bringup/waypoints.py indoor-navigation/src/indoor_nav_bringup/package.xml indoor-navigation/tests/test_session_processes.py indoor-navigation/tests/test_waypoints.py
git commit -m "feat(indoor-navigation): serve waypoint actions"
```

---

### Task 3: Add waypoint interfaces to the reusable Lichtblick adapter

**Files:**
- Modify: `shared/lichtblick-robot-control/src/panelConfig.ts`
- Modify: `shared/lichtblick-robot-control/src/panelConfig.test.ts`
- Modify: `shared/lichtblick-robot-control/src/lichtblickAdapter.ts`
- Modify: `shared/lichtblick-robot-control/src/lichtblickAdapter.test.ts`

**Interfaces:**
- Consumes: `/waypoints/available`, `/session_manager.waypoint_name`, and the three Trigger services.
- Produces: normalized config fields, `AdapterSnapshot.waypoints: string[]`, and `runWaypointAction(name, actionKey)`.

- [ ] **Step 1: Write failing configuration tests**

Require defaults:

```typescript
assert.equal(DEFAULT_CONFIG.availableWaypointsTopic, "/waypoints/available");
assert.equal(DEFAULT_CONFIG.waypointNameParameter, "/session_manager.waypoint_name");
assert.equal(DEFAULT_CONFIG.saveWaypointService, "/waypoints/save");
assert.equal(DEFAULT_CONFIG.navigateWaypointService, "/waypoints/navigate");
assert.equal(DEFAULT_CONFIG.deleteWaypointService, "/waypoints/delete");
```

Require older partial state to normalize all missing waypoint fields and reuse the validated/deduplicated/sorted name parser for newline-separated waypoint names.

- [ ] **Step 2: Run config tests and verify RED**

Run: `cd shared/lichtblick-robot-control && npx tsx --test src/panelConfig.test.ts`

Expected: missing waypoint config properties.

- [ ] **Step 3: Implement normalized waypoint configuration**

Add the five string fields to `PanelConfig`, `DEFAULT_CONFIG`, `stringKeys`, and the settings editor. Keep config compatibility by normalizing absent fields individually; set the normalized schema version to `2` and update the mapping layout in Task 4.

- [ ] **Step 4: Run config tests and verify GREEN**

Run: `cd shared/lichtblick-robot-control && npx tsx --test src/panelConfig.test.ts`

Expected: config tests pass.

- [ ] **Step 5: Write failing adapter tests**

Require subscription to `/waypoints/available`, parsing into `snapshot.waypoints`, and the parameter/service sequence:

```typescript
const action = adapter.runWaypointAction("Kitchen", "navigateWaypointService");
assert.deepEqual(calls.parameters.at(-1), ["/session_manager.waypoint_name", "Kitchen"]);
assert.equal(calls.services.length, 0);
fixture.render({ parameters: new Map([["/session_manager.waypoint_name", "Kitchen"]]) });
await action;
assert.deepEqual(calls.services.at(-1), { service: "/waypoints/navigate", request: {} });
```

Also require invalid-name rejection, Trigger refusal surfacing, and a success message that says the request was sent rather than reached.

- [ ] **Step 6: Run adapter tests and verify RED**

Run: `cd shared/lichtblick-robot-control && npx tsx --test src/lichtblickAdapter.test.ts`

Expected: missing subscription, snapshot field, and action method.

- [ ] **Step 7: Implement the adapter behavior**

Add `WaypointActionConfigKey`, parse the new String topic, and implement `runWaypointAction` through a generalized `setParameterAndWait(parameter, value)`. Resolve a pending parameter when `renderState.parameters.get(pending.parameter) === pending.expected`; make timeout copy say “parameter acknowledgement” rather than “map-name parameter acknowledgement.”

- [ ] **Step 8: Run adapter tests and the extension suite**

Run: `npm test --prefix shared/lichtblick-robot-control`

Expected: all extension and deployment tests pass.

- [ ] **Step 9: Commit the adapter**

```bash
git add shared/lichtblick-robot-control/src/panelConfig.ts shared/lichtblick-robot-control/src/panelConfig.test.ts shared/lichtblick-robot-control/src/lichtblickAdapter.ts shared/lichtblick-robot-control/src/lichtblickAdapter.test.ts
git commit -m "feat(shared): add waypoint control interfaces"
```

---

### Task 4: Render waypoint controls and ship the updated app contract

**Files:**
- Modify: `shared/lichtblick-robot-control/src/RobotControlPanel.tsx`
- Modify: `shared/lichtblick-robot-control/src/RobotControlPanel.test.tsx`
- Modify: `shared/lichtblick-robot-control/src/styles.css`
- Modify: `shared/lichtblick-robot-control/package.json`
- Modify: `shared/lichtblick-robot-control/package-lock.json`
- Modify: `shared/lichtblick-robot-control/README.md`
- Modify: `shared/lichtblick-robot-control/CHANGELOG.md`
- Modify: `indoor-navigation/lichtblick/mapping-layout.json`
- Modify: `indoor-navigation/tests/test_lichtblick_control_layout.py`
- Modify: `indoor-navigation/docker/Dockerfile`
- Modify: `indoor-navigation/Makefile`
- Modify: `indoor-navigation/README.md`
- Modify: `REGISTRY.md`

**Interfaces:**
- Consumes: `snapshot.waypoints` and `runWaypointAction` from Task 3.
- Produces: operator-facing waypoint save/list/navigate/delete controls and Robot Control version `0.5.0`.

- [ ] **Step 1: Write failing panel tests**

Extend the fixture with waypoint calls and require:

```typescript
assert.ok(document.querySelector('[aria-label="Save current position"]'));
assert.deepEqual(
  [...document.querySelectorAll('[data-waypoint-name]')].map((row) => row.getAttribute('data-waypoint-name')),
  ["Kitchen", "Lobby"],
);
```

Enter `Kitchen`, click Save, and require `runWaypointAction("Kitchen", "saveWaypointService")`. Click Navigate/Delete for an existing row and require the corresponding calls. Prove every action is disabled outside `LOCALIZATION`, invalid names cannot save, and keyboard driving remains inactive while the waypoint input owns focus.

- [ ] **Step 2: Run panel tests and verify RED**

Run: `cd shared/lichtblick-robot-control && npx tsx --test src/RobotControlPanel.test.tsx`

Expected: missing Waypoints card and controls.

- [ ] **Step 3: Implement the compact Waypoints card**

Add local `waypointName` state, validation, a `runWaypointAction` callback, and a card after Maps. Each row renders its name plus Navigate/Delete buttons. Gate all actions on `snapshot.mode === "LOCALIZATION"`, `snapshot.busy`, service capability, and valid inputs. Reuse the existing compact visual tokens and add only row/grid styles needed to keep names readable at the 24% rail width.

- [ ] **Step 4: Run panel tests and verify GREEN**

Run: `cd shared/lichtblick-robot-control && npx tsx --test src/RobotControlPanel.test.tsx`

Expected: panel tests pass.

- [ ] **Step 5: Update layout defaults and versioned extension artifact**

Set Robot Control to `0.5.0` in `package.json` and lockfile, update the `.foxe` filename in Dockerfile/Makefile/docs, and add a changelog entry. Extend `mapping-layout.json` with config version `2` and the five waypoint interfaces. Update the exact-state layout test before changing the JSON so it fails for the missing fields, then rerun it after the layout change.

- [ ] **Step 6: Update user documentation and registry**

Document the localization workflow: load a map, enter a waypoint name, save the robot's current pose, then Navigate/Delete. State that sidecars are local per-map data and navigation acceptance is not arrival. Update the registry card's verified description without claiming a smoke pass until Step 8 succeeds.

- [ ] **Step 7: Run all static and unit gates**

Run:

```bash
docker run --rm indoor-navigation:latest bash -lc 'cd /ws && . install/setup.bash && python3 -m unittest discover -s tests -p "test_*.py" -v'
npm test --prefix shared/lichtblick-robot-control
npm run lint --prefix shared/lichtblick-robot-control
npm run build --prefix shared/lichtblick-robot-control
npm run package --prefix shared/lichtblick-robot-control
git diff --check
```

Expected: every command exits 0 and packages `robium.robot-control-0.5.0.foxe`.

- [ ] **Step 8: Run the real navigation smoke**

First confirm no interactive mapping container is running. Then run `make -C indoor-navigation smoke`. Expected: both known goals return `TaskResult.SUCCEEDED`, `PASS: all goals reached`, and exit 0. Do not exercise waypoint saving against the worktree's real map mount.

- [ ] **Step 9: Confirm saved maps remain untouched**

Run `git status --short` and compare the two pre-existing untracked directories. Expected: they remain untracked and unstaged, with no waypoint sidecar created by verification.

- [ ] **Step 10: Commit the UI, contract, and docs**

```bash
git add shared/lichtblick-robot-control indoor-navigation/lichtblick/mapping-layout.json indoor-navigation/tests/test_lichtblick_control_layout.py indoor-navigation/docker/Dockerfile indoor-navigation/Makefile indoor-navigation/README.md REGISTRY.md
git commit -m "feat(indoor-navigation): add named waypoint controls"
```
