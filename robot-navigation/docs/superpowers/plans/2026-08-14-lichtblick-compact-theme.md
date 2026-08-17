# Compact Lichtblick Control Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Robot Control visually follow Lichtblick and keep every existing control visible in the screenshot-sized right rail with spare vertical capacity.

**Architecture:** Preserve the React structure and all ROS behavior. Replace only the extension's visual tokens and density rules, using the existing `light`/`dark` root class as the theme boundary and real bundled-viewer geometry as the regression contract.

**Tech Stack:** React 18, CSS, Lichtblick extension packaging, Docker, in-app browser verification.

## Global Constraints

- Do not change ROS topics, services, parameters, control labels, behavior, or layout split percentages.
- Do not hide or collapse any of the nine controls.
- Light and dark modes must both use neutral Lichtblick-compatible surfaces.
- The root remains vertically scrollable below the acceptance viewport.
- Follow TDD: observe the current geometry/theme failure before modifying production CSS.

---

### Task 1: Compact and theme the panel

**Files:**
- Modify: `shared/lichtblick-robot-control/src/styles.css`
- Verify: `shared/lichtblick-robot-control/src/RobotControlPanel.test.tsx`

**Interfaces:**
- Consumes: existing `.robot-control.light` / `.robot-control.dark` classes and unchanged component markup.
- Produces: a dense, theme-native control panel that still exposes all existing accessible controls.

- [x] **Step 1: Record the failing visual contract**

Build and launch the current extension in the bundled viewer. At a 2048×1152 application viewport, measure the Robot Control root and Quick Actions rectangle. Confirm that the Quick Actions bottom exceeds the visible panel bottom or is clipped and record the current computed root/card colors.

- [x] **Step 2: Replace hard-coded branding with theme-native tokens**

Set neutral light/dark `--bg`, `--card`, `--line`, `--text`, and `--muted` values; retain teal only for `--accent`; remove the radial/linear gradient and backdrop blur.

- [x] **Step 3: Reduce vertical density**

Reduce outer padding to 10px, card gap/padding to 8–10px, control height to 30–32px, WASD cells to 44–48px, heading sizes, pill padding, label margins, hint spacing, and shadow strength. Keep the existing narrow-panel stacking media query.

- [x] **Step 4: Run extension checks**

Run `make control-extension-check` from `robot-navigation`. Expected: all component and storage tests, lint, build, and package pass.

- [x] **Step 5: Rebuild and verify the real viewer**

Run `make build`, launch mapping, reload a clean browser origin, and repeat the exact geometry/color measurement. Expected: all nine controls and the Quick Actions bottom are within the visible panel, with neutral light-mode colors and remaining vertical space.

- [x] **Step 6: Run app and robotics regression gates**

Run the five Lichtblick host tests, image asset contract, `git diff --check`, and `make smoke`. Expected: zero failures and two successful Nav2 goals.

- [x] **Step 7: Commit the compact theme**

Commit the CSS, spec, plan, and any documentation/evidence updates as `fix(robot-navigation): compact Lichtblick controls`.
