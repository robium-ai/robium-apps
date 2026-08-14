# Idle Sessions and Simulation Worlds Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Start the interactive dashboard without a map publisher and let operators explicitly start mapping, stop-and-save mapping, load localization, and restart Gazebo in one of four curated worlds.

**Architecture:** Keep the dashboard, Foxglove bridge, teleop relay, and a new ROS session manager alive in the top-level launch. The manager owns separate Gazebo and navigation child process groups, publishes latched session/world state, and performs mutually exclusive transitions; the reusable Lichtblick panel drives it through parameters and Trigger services.

**Tech Stack:** ROS 2 Jazzy, Python/rclpy, ROS launch, Gazebo Harmonic/Fuel, React 18, TypeScript, Lichtblick extension API, Python unittest, Node test runner, Docker Compose.

## Global Constraints

- Startup state is `IDLE`; no SLAM, map server, AMCL, or `/map` publisher runs until explicitly requested.
- Worlds are `house`, `tugbot_warehouse`, `industrial_warehouse`, and `living_room`.
- Fuel references remain upstream and pinned to the verified current versions: OpenRobotics Tugbot in Warehouse v2, OpenRobotics industrial-warehouse v4, and makerspet living_room v1.
- Restarting simulation stops navigation first and returns the session to `IDLE`.
- Maps are stored and listed per world under `/ws/maps/<world>/`.
- Preserve compact panel styling, dynamic status/errors, movement speed sliders, WASD, Go home, and Stop robot.

---

### Task 1: Session process state machine

**Files:**
- Create: `indoor-navigation/src/indoor_nav_bringup/indoor_nav_bringup/session_processes.py`
- Create: `indoor-navigation/tests/test_session_processes.py`

**Interfaces:**
- Produces: `SessionProcesses(factory, maps_root, initial_world)`, `start_mapping(name)`, `stop_mapping(save)`, `load_map(name)`, `restart_simulation(world)`, and `close()`.

- [x] Write tests proving startup creates only the simulation child and reports IDLE, mode changes are mutually exclusive, stopping invokes save before terminating navigation, missing maps are rejected, and world restart stops navigation then simulation and restores IDLE.
- [x] Run `python3 -m unittest tests.test_session_processes -v` and verify failures identify the missing module.
- [x] Implement the smallest injected process manager that passes those behavior tests, with validated map/world names and explicit process-group shutdown.
- [x] Re-run the focused tests and verify all pass.

### Task 2: ROS session manager and restartable launch composition

**Files:**
- Create: `indoor-navigation/src/indoor_nav_bringup/indoor_nav_bringup/session_manager.py`
- Create: `indoor-navigation/src/indoor_nav_bringup/launch/navigation_stack.launch.py`
- Modify: `indoor-navigation/src/indoor_nav_bringup/launch/mapping.launch.py`
- Modify: `indoor-navigation/src/indoor_nav_bringup/launch/sim.launch.py`
- Modify: `indoor-navigation/src/indoor_nav_bringup/setup.py`
- Modify: `indoor-navigation/src/indoor_nav_bringup/package.xml`
- Modify: `indoor-navigation/tests/test_launch_modes.py`

**Interfaces:**
- Produces: parameters `/session_manager.map_name` and `/session_manager.world`; services `/mapping/start`, `/mapping/stop`, `/mapping/load`, `/simulation/restart`; topics `/mapping/state`, `/maps/available`, `/simulation/state`.

- [x] Add failing launch tests for four Fuel/local world resolutions, per-world spawn poses, optional Foxglove bridge, and a top-level mapping launch containing a session manager but no eagerly included SLAM/localization stack.
- [x] Run the focused launch tests and verify RED.
- [x] Add pinned Fuel URIs and spawn poses to `sim.launch.py`; extract the mapping/localization-only child launch; implement the ROS wrapper around `SessionProcesses`; make `mapping.launch.py` own stable bridge/viz/teleop/session nodes.
- [x] Re-run session and launch tests and verify GREEN.

### Task 3: Reusable Simulation panel and corrected mapping actions

**Files:**
- Modify: `shared/lichtblick-robot-control/src/panelConfig.ts`
- Modify: `shared/lichtblick-robot-control/src/panelConfig.test.ts`
- Modify: `shared/lichtblick-robot-control/src/lichtblickAdapter.ts`
- Modify: `shared/lichtblick-robot-control/src/lichtblickAdapter.test.ts`
- Modify: `shared/lichtblick-robot-control/src/RobotControlPanel.tsx`
- Modify: `shared/lichtblick-robot-control/src/RobotControlPanel.test.tsx`
- Modify: `shared/lichtblick-robot-control/src/styles.css`
- Modify: `indoor-navigation/lichtblick/mapping-layout.json`
- Modify: `indoor-navigation/tests/test_lichtblick_control_layout.py`

**Interfaces:**
- Adds config fields `simulationStateTopic`, `worldParameter`, and `restartSimulationService`; adds `runSimulationAction(world)`.

- [x] Add failing config, adapter, component, and layout tests for corrected service names, IDLE button states, the four-world selector, parameter acknowledgement before restart, and compact rendering.
- [x] Run the focused Node/Python tests and verify RED.
- [x] Implement the config migration/defaults, topic parsing, simulation action, compact Simulation card, and corrected mapping gates.
- [x] Re-run the focused tests and verify GREEN.

### Task 4: Container integration, documentation, and real smoke

**Files:**
- Modify: `indoor-navigation/docker/compose.yaml`
- Modify: `indoor-navigation/Makefile`
- Modify: `indoor-navigation/README.md`
- Modify: `indoor-navigation/docs/architecture-brief.md`
- Modify: `indoor-navigation/docs/superpowers/plans/2026-08-14-idle-sessions-and-simulation-worlds.md` (checkboxes only)
- Modify: `REGISTRY.md`

**Interfaces:**
- Produces: default interactive profile using the supervisor and documented test workflow.

- [x] Update compose/default commands and documentation for the IDLE-first workflow and first-use Fuel download behavior.
- [x] Run all extension and app unit tests, linters, build/package checks, and `git diff --check`.
- [x] Rebuild the Docker image, launch the mapping profile, verify `/mapping/state` is IDLE and `/map` has zero publishers, exercise mapping start/stop, and switch at least one Fuel world.
- [x] Inspect the real 1024x576 Lichtblick panel and verify all controls remain visible.
- [x] Run the navigation smoke and update REGISTRY verified metadata.
