# Furnished House Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the broken Living Room simulation with a pinned, furnished AWS Small House environment that supports the dashboard's full TurtleBot mapping workflow.

**Architecture:** Fetch the pinned MIT-licensed AWS asset during the Docker build, prepare its legacy world for Gazebo Harmonic in the bringup launch layer, and route the existing session-manager and control-panel interfaces through a new `furnished_house` world identifier. Keep external assets out of git and preserve per-world map isolation.

**Tech Stack:** ROS 2 Jazzy, Gazebo Harmonic, Python launch, Docker, React/TypeScript Lichtblick extension.

## Global Constraints

- Pin AWS Small House to commit `ff9631ca6d1db9c1ba656498151464b5ab74aafe`.
- Preserve the upstream MIT license and source metadata in the image.
- Do not modify or delete existing user maps under `maps/living_room/`.
- Verify sensor messages and mapping behavior in the real container, not only unit tests.

---

### Task 1: Pinned asset acquisition

**Files:**
- Create: `indoor-navigation/scripts/fetch_aws_small_house.py`
- Modify: `indoor-navigation/docker/Dockerfile`
- Test: `indoor-navigation/tests/test_aws_small_house_asset.py`

**Interfaces:**
- Produces `/opt/robium/worlds/aws-small-house/{models,worlds,LICENSE,SOURCE}` in the image.

- [ ] Write a failing test that downloads a local tar fixture, validates the expected commit marker and rejects archive traversal.
- [ ] Run the targeted test and confirm it fails because the fetcher is absent.
- [ ] Implement the pinned archive fetch/extract helper and Docker build invocation.
- [ ] Run the targeted test and full Python suite.

### Task 2: Harmonic world preparation and backend routing

**Files:**
- Modify: `indoor-navigation/src/indoor_nav_bringup/launch/sim.launch.py`
- Modify: `indoor-navigation/src/indoor_nav_bringup/indoor_nav_bringup/session_processes.py`
- Modify: `indoor-navigation/tests/test_launch_modes.py`
- Modify: `indoor-navigation/tests/test_session_processes.py`

**Interfaces:**
- Consumes `/opt/robium/worlds/aws-small-house/worlds/small_house.world` and its model tree.
- Produces dashboard world value `furnished_house` and a prepared Gazebo Harmonic world path.

- [ ] Write failing tests for the new identifier, source path, modern system plugins, and removal of `living_room`.
- [ ] Run the targeted tests and confirm the expected failures.
- [ ] Implement the minimal world preparation and spawn-pose routing.
- [ ] Run targeted tests and the full Python suite.

### Task 3: Control panel and documentation

**Files:**
- Modify: `shared/lichtblick-robot-control/src/panelConfig.ts`
- Modify: `shared/lichtblick-robot-control/src/RobotControlPanel.test.tsx`
- Modify: `shared/lichtblick-robot-control/README.md`
- Modify: `shared/lichtblick-robot-control/CHANGELOG.md`
- Modify: `indoor-navigation/README.md`
- Modify: `REGISTRY.md`

**Interfaces:**
- Produces a `Furnished House` dropdown option backed by `furnished_house`.

- [ ] Write a failing panel test expecting Furnished House and no Living Room.
- [ ] Run it and confirm it fails against the current options.
- [ ] Update the option and operator documentation.
- [ ] Run tests, lint, build, and package the extension.

### Task 4: End-to-end verification

**Files:**
- Modify: `indoor-navigation/docs/superpowers/plans/2026-08-14-furnished-house.md` to check completed steps.

**Interfaces:**
- Verifies the built image, ROS topics, motion, and mapping lifecycle.

- [ ] Build and force-recreate the mapping container.
- [ ] Restart into Furnished House through the dashboard service path.
- [ ] Verify `/scan`, `/camera/image_raw`, `/odom`, and `/clock` messages.
- [ ] Publish teleop velocity and verify odometry changes.
- [ ] Start mapping, verify `/map`, stop mapping, and verify `IDLE` with no `/map` publisher.
- [ ] Run `git diff --check`, both full test suites, and review the final diff.
