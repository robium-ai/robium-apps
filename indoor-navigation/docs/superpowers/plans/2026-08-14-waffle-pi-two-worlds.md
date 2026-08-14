# Waffle Pi and Two Simulation Worlds Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make TurtleBot3 Waffle Pi the only robot and reduce the simulator selector to House and Warehouse.

**Architecture:** Keep stable backend identifiers for per-world maps, but expose two short labels in the Lichtblick panel. Select the upstream Waffle Pi model through the existing TurtleBot3 environment-variable boundary, tune its camera rate in the same build/native setup stages, and adopt its upstream 0.15 m Nav2 radius.

**Tech Stack:** ROS 2 Jazzy, Gazebo Harmonic, Nav2, Python launch/configuration, Docker, React/TypeScript Lichtblick extension.

## Global Constraints

- The only accepted worlds are `furnished_house` and `tugbot_warehouse`.
- Visible labels are exactly `House` and `Warehouse`; House is the default.
- The only controllable robot is `waffle_pi`.
- Preserve all existing map files and keep internal map directory names unchanged.
- Preserve `/cmd_vel`, `/odom`, `/tf`, `/imu`, `/scan`, and camera ROS interfaces.

---

### Task 1: Two-world session and panel contract

**Files:**
- Modify: `src/indoor_nav_bringup/launch/sim.launch.py`
- Modify: `src/indoor_nav_bringup/launch/mapping.launch.py`
- Modify: `src/indoor_nav_bringup/indoor_nav_bringup/session_processes.py`
- Modify: `tests/test_launch_modes.py`
- Modify: `tests/test_session_processes.py`
- Modify: `../shared/lichtblick-robot-control/src/panelConfig.ts`
- Modify: `../shared/lichtblick-robot-control/src/RobotControlPanel.test.tsx`

**Interfaces:**
- Consumes: existing `world` session parameter and `WORLD_OPTIONS` panel configuration.
- Produces: accepted values `furnished_house | tugbot_warehouse`, displayed as `House | Warehouse`.

- [ ] Write failing backend and panel tests expecting two worlds and `furnished_house` as the default.
- [ ] Run targeted Python and TypeScript tests and confirm they fail on the four-world contract.
- [ ] Remove the obsolete world routes/options and set the new default without renaming internal identifiers.
- [ ] Run targeted tests and commit the green two-world contract.

### Task 2: Waffle Pi runtime profile

**Files:**
- Modify: `docker/compose.yaml`
- Modify: `docker/Dockerfile`
- Modify: `robium-app.yaml`
- Modify: `scripts/native_paths.py`
- Modify: `scripts/native_setup.py`
- Modify: `src/indoor_nav_bringup/config/nav2_params.yaml`
- Modify: `src/indoor_nav_bringup/launch/sim.launch.py`
- Modify: `src/indoor_nav_bringup/indoor_nav_bringup/teleop_relay.py`
- Modify: `tests/test_native_paths.py`
- Modify: `tests/test_native_setup.py`
- Create: `tests/test_robot_profile.py`

**Interfaces:**
- Consumes: upstream `turtlebot3_waffle_pi` SDF, bridge YAML, URDF, and Nav2 radius.
- Produces: `TURTLEBOT3_MODEL=waffle_pi`, a 10 Hz pinhole camera, and 0.15 m local/global costmap radii.

- [ ] Write failing tests for the Waffle Pi environment, camera optimization behavior, and both costmap radii.
- [ ] Run targeted Python tests and confirm failures identify Burger Cam and 0.10 m assumptions.
- [ ] Switch all runtime environments to Waffle Pi, generalize camera optimization, and set both radii to 0.15 m.
- [ ] Run targeted tests and commit the green robot profile.

### Task 3: Documentation and live verification

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture-brief.md`
- Modify: `../shared/lichtblick-robot-control/README.md`
- Modify: `../shared/lichtblick-robot-control/CHANGELOG.md`
- Modify: `../REGISTRY.md`
- Modify: `docs/superpowers/plans/2026-08-14-waffle-pi-two-worlds.md`

**Interfaces:**
- Verifies the built Waffle Pi image and the two-world operator workflow.

- [ ] Update operator and registry text to describe Waffle Pi, House, and Warehouse.
- [ ] Build and force-recreate the mapping container; confirm initial `furnished_house`, `IDLE`, and no `/map`.
- [ ] Verify `/clock`, `/scan`, `/camera/image_raw`, and `/odom`, then publish teleop and confirm odometry changes.
- [ ] Restart into Warehouse and repeat the sensor checks.
- [ ] Start and stop mapping, verify saved output, return to `IDLE`, then move only generated smoke artifacts out of the workspace.
- [ ] Run all Python and extension tests, lint, production build/package, and `git diff --check`.
- [ ] Check every completed box in this plan and commit documentation plus verification evidence.

