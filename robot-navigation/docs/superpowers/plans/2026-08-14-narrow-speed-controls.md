# Narrow Robot Control and Speed Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fit Robot Control in a 24% Lichtblick right rail and let operators adjust persisted forward and turn speeds directly in Movement.

**Architecture:** Extend the existing `ControlPanelAdapter` surface with `updateConfig`, reuse `LichtblickAdapter.updateConfig` for persistence and drive-controller refresh, and simplify only the React markup and CSS. Keep ROS interfaces and behavior unchanged; change the mapping layout split from 72/28 to 76/24.

**Tech Stack:** React 18, TypeScript, CSS, Lichtblick extension API, Python `unittest`, Docker Compose.

## Global Constraints

- Forward speed range is `0.05`–`0.50` m/s with step `0.05`.
- Turn speed range is `0.10`–`1.50` rad/s with step `0.10`.
- Preserve all nine accessible action/direction buttons and all ROS interface configuration.
- Remove eyebrow copy, direction captions, static helper hints, the speed badge, and the ROS-ready badge.
- Keep dynamic errors and status messages.

---

### Task 1: Persisted movement speed sliders

**Files:**
- Modify: `shared/lichtblick-robot-control/src/RobotControlPanel.tsx`
- Modify: `shared/lichtblick-robot-control/src/RobotControlPanel.test.tsx`

**Interfaces:**
- Consumes: `PanelConfig`, `LichtblickAdapter.updateConfig(patch: Partial<PanelConfig>): void`.
- Produces: `ControlPanelAdapter.updateConfig` and range inputs named `Forward speed` and `Turn speed`.

- [x] **Step 1: Write the failing component test**

Add an `updates` array and `updateConfig` mock to the fixture. Assert both sliders' bounds and initial values, dispatch an input/change to the forward slider, and expect `{ linearSpeed: 0.35 }` in `updates`.

- [x] **Step 2: Run the focused test and verify RED**

Run: `npm test --prefix ../shared/lichtblick-robot-control -- --test-name-pattern "updates movement speeds"`

Expected: FAIL because `Forward speed` does not exist.

- [x] **Step 3: Add the adapter method and slider markup**

Add `updateConfig(patch: Partial<Pick<PanelConfig, "linearSpeed" | "angularSpeed">>): void` to `ControlPanelAdapter`, import `PanelConfig`, and render two labeled range inputs. Parse each value with `Number(event.currentTarget.value)` and pass the corresponding one-property patch to `adapter.updateConfig`.

- [x] **Step 4: Run the focused test and verify GREEN**

Run the Step 2 command. Expected: PASS.

### Task 2: Remove secondary copy and narrow the rail

**Files:**
- Modify: `shared/lichtblick-robot-control/src/RobotControlPanel.tsx`
- Modify: `shared/lichtblick-robot-control/src/RobotControlPanel.test.tsx`
- Modify: `shared/lichtblick-robot-control/src/styles.css`
- Modify: `robot-navigation/lichtblick/mapping-layout.json`
- Modify: `robot-navigation/tests/test_lichtblick_control_layout.py`

**Interfaces:**
- Consumes: existing button `aria-label` values and `.robot-control.light` / `.dark` theme classes.
- Produces: 76/24 mapping split and compact `.speed-controls` / `.speed-control` styling.

- [x] **Step 1: Write failing copy and layout tests**

Assert the rendered text excludes `ROBIUM / NAVIGATION`, `Forward`, `ROS ready`, and `Hold a button`; assert the four direction buttons still exist by `aria-label`. Change the Python layout expectation and test name from 72/28 to 76/24.

- [x] **Step 2: Run both focused tests and verify RED**

Run:

```bash
npm test --prefix ../shared/lichtblick-robot-control -- --test-name-pattern "removes secondary copy"
python3 -m unittest tests.test_lichtblick_control_layout -v
```

Expected: React test finds current helper copy; Python test receives `72` instead of `76`.

- [x] **Step 3: Simplify markup, add compact CSS, and update layout**

Remove `.eyebrow`, `.speed-readout`, `.connection-dot`, and static `.hint` markup. Render only the W/A/S/D letter in each drive button. Add a two-column `.speed-controls` grid with compact labels and range inputs; keep one column below 220px. Set mapping layout root `splitPercentage` to `76`.

- [x] **Step 4: Run both focused tests and verify GREEN**

Run the Step 2 commands. Expected: all selected tests pass.

### Task 3: Full packaging and real-view verification

**Files:**
- Modify: `robot-navigation/docs/superpowers/plans/2026-08-14-narrow-speed-controls.md` (checkboxes only)

**Interfaces:**
- Consumes: packaged `.foxe`, fingerprinted preinstall bootstrap, mapping Docker profile.
- Produces: verified narrow default panel.

- [x] **Step 1: Run extension and host gates**

Run:

```bash
make control-extension-check
python3 -m unittest discover -s tests -p 'test_lichtblick*.py' -v
git diff --check
```

Expected: 0 failures.

- [x] **Step 2: Build and inspect the real Lichtblick view**

Run `make build`, start the mapping profile, and inspect at 1024×576. Verify the right rail is 24%, both sliders and all nine controls are visible, and removed copy/badges do not appear.

- [x] **Step 3: Run the isolated navigation smoke**

Stop the mapping profile, then run `make smoke`. Expected: both goals return `TaskResult.SUCCEEDED` and `PASS: all goals reached`.

- [x] **Step 4: Commit implementation**

Commit as `feat(robot-navigation): add compact speed controls`.
