# Lichtblick Dashboard Extension Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename Robot Control to Robium Dashboard and make one reusable Lichtblick extension configurable for different robot apps.

**Architecture:** The shared `.foxe` owns the reusable dashboard UI and ROS interaction mechanics. Each app's committed Lichtblick layout enables only the capabilities it needs and supplies its ROS interfaces and simulation choices; indoor-navigation enables the complete navigation dashboard.

**Tech Stack:** TypeScript, React, `@lichtblick/suite`, Lichtblick layout JSON, Docker

## Global Constraints

- Do not create, restore, or run automated tests; the maintainer explicitly chose runtime-only validation for this prototype.
- Preserve the untracked saved maps under `indoor-navigation/src/indoor_nav_bringup/maps/`.
- Keep the extension open-source and app-configurable; the `.foxe` is a compiled artifact, not an editing surface.
- Do not publish a GitHub Release in this task.

---

### Task 1: Rename the shared extension

**Files:**
- Rename: `shared/lichtblick-robot-control/` to `shared/lichtblick-dashboard/`
- Modify: `shared/lichtblick-dashboard/package.json`
- Modify: `shared/lichtblick-dashboard/package-lock.json`
- Modify: `shared/lichtblick-dashboard/src/index.ts`
- Modify: `shared/lichtblick-dashboard/src/RobotControlPanel.tsx`
- Modify: `shared/lichtblick-dashboard/src/styles.css`

**Interfaces:**
- Produces: package identity `robium.dashboard`, panel type `Robium Dashboard.dashboard`, and artifact `robium.dashboard-0.9.0.foxe`.

- [x] Rename the directory and source component to Dashboard naming.
- [x] Change the package name, display name, description, panel registration, default title, visible heading, and CSS root class.
- [x] Bump the extension to `0.9.0` and add a changelog entry.

### Task 2: Add app-selectable dashboard capabilities

**Files:**
- Modify: `shared/lichtblick-dashboard/src/panelConfig.ts`
- Modify: `shared/lichtblick-dashboard/src/lichtblickAdapter.ts`
- Modify: `shared/lichtblick-dashboard/src/DashboardPanel.tsx`

**Interfaces:**
- Produces: config version 4 with `showMovement`, `showMaps`, `showNavigation`, `showSimulation`, `showQuickActions`, and `simulationWorlds`.
- Consumes: saved panel state and app-provided layout configuration.

- [x] Make the generic default Movement-only, including the Stop Robot safety action.
- [x] Add boolean capability controls to the Lichtblick settings sidebar.
- [x] Subscribe, advertise, render, and invoke only enabled capabilities.
- [x] Move simulation world values and labels into app configuration.
- [x] Preserve migration of existing version-3 indoor-navigation state as a full dashboard.

### Task 3: Configure indoor-navigation as a full dashboard consumer

**Files:**
- Modify: `indoor-navigation/lichtblick/mapping-layout.json`
- Modify: `indoor-navigation/Makefile`
- Modify: `indoor-navigation/docker/Dockerfile`
- Modify: `indoor-navigation/docker/Dockerfile.dockerignore`
- Modify: `indoor-navigation/scripts/bundle_default_extension.py`

**Interfaces:**
- Consumes: `Robium Dashboard.dashboard` and config version 4.
- Produces: the existing full indoor-navigation UI with House and Warehouse choices.

- [x] Enable all indoor-navigation dashboard capabilities in its layout.
- [x] Update Docker build, browser preinstall, and Make targets to the renamed package and artifact.
- [x] Keep the existing camera, 3D, logs, and right-rail layout geometry unchanged.

### Task 4: Document reuse and ownership

**Files:**
- Modify: `shared/lichtblick-dashboard/README.md`
- Modify: `indoor-navigation/README.md`
- Modify: `indoor-navigation/docs/architecture-brief.md`
- Modify: `REGISTRY.md`

**Interfaces:**
- Produces: documentation for configuration-first reuse, source customization, companion panels, and future GitHub Release distribution.

- [x] Document the developer flow: install Dashboard, configure capabilities/interfaces, and commit the layout.
- [x] Document that advanced customization edits TypeScript source or adds a companion panel, never edits `.foxe` directly.
- [x] Update indoor-navigation and registry references to Dashboard.

### Task 5: Static verification and commit

**Files:**
- Inspect: all modified files

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces: a committed generic Dashboard integration without touching saved maps.

- [x] Inspect the diff and search active files for stale Robot Control package references.
- [x] Review JSON syntax and TypeScript/config consistency without invoking build, lint, or test commands.
- [x] Commit the scoped changes while leaving saved maps untracked.
