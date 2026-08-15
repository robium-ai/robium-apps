# Navigation Status and Stop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a combined Navigation/Waypoints card with live goal status and cancellation.

**Architecture:** Session Manager adapts Nav2's hidden action status and cancel service into stable String/Trigger interfaces. Robot Control consumes those generic interfaces and merges waypoint controls into the Navigation card.

**Tech Stack:** Python 3, ROS 2 Jazzy, `rclpy`, `action_msgs`, TypeScript 5, React 18, Lichtblick extension SDK, JSON, CSS.

## Global Constraints

- Do not add or run automated tests, lint, build, or smoke checks.
- Preserve Stop Robot's zero-velocity behavior.
- Leave saved maps and waypoint sidecars untouched and unstaged.

---

### Task 1: Adapt Nav2 navigation state

**Files:**
- Modify: `indoor-navigation/src/indoor_nav_bringup/indoor_nav_bringup/session_manager.py`
- Modify: `indoor-navigation/src/indoor_nav_bringup/package.xml`

- [ ] Subscribe to `GoalStatusArray` and publish latched `NAVIGATING` or `IDLE` state.
- [ ] Add `/navigation/stop` Trigger backed by Nav2's cancel-all request.
- [ ] Declare the `action_msgs` runtime dependency.

### Task 2: Merge navigation and waypoints in Robot Control

**Files:**
- Modify: `shared/lichtblick-robot-control/src/panelConfig.ts`
- Modify: `shared/lichtblick-robot-control/src/lichtblickAdapter.ts`
- Modify: `shared/lichtblick-robot-control/src/RobotControlPanel.tsx`
- Modify: `shared/lichtblick-robot-control/src/styles.css`

- [ ] Add `navigationStateTopic` and normalize it into the adapter snapshot.
- [ ] Replace the Waypoints heading with Navigation status and Stop navigation.
- [ ] Keep the waypoint controls in the same card below the status controls.
- [ ] Configure Stop Robot to cancel navigation through the now-default stop service.

### Task 3: Clean visibility and ship version 0.7.0

**Files:**
- Modify: `indoor-navigation/lichtblick/mapping-layout.json`
- Modify: `shared/lichtblick-robot-control/package.json`
- Modify: `shared/lichtblick-robot-control/package-lock.json`
- Modify: `shared/lichtblick-robot-control/CHANGELOG.md`
- Modify: `shared/lichtblick-robot-control/README.md`
- Modify: `indoor-navigation/Makefile`
- Modify: `indoor-navigation/docker/Dockerfile`
- Modify: `indoor-navigation/README.md`

- [ ] Make normal navigation topics explicit and hide duplicate/debug topics.
- [ ] Reduce laser-scan point size to 2.
- [ ] Bump config schema to 3 and extension artifact to 0.7.0.
- [ ] Document the combined Navigation card and its ROS interfaces.
- [ ] Commit and push without staging local runtime map data.
