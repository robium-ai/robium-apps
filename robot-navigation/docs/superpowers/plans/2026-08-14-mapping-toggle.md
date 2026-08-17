# Mapping Toggle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Put the map-name field and one Start/Finish mapping button on the same row.

**Architecture:** Robot Control derives the button label and service from the existing mapping mode. No backend interface changes are needed.

**Tech Stack:** TypeScript 5, React 18, CSS, Lichtblick extension SDK, Markdown.

## Global Constraints

- Do not add or run automated tests, lint, build, or smoke checks.
- Preserve existing ROS interfaces and map-name validation.
- Do not stage local runtime map data.

---

### Task 1: Add the state-aware mapping row

**Files:**
- Modify: `shared/lichtblick-robot-control/src/RobotControlPanel.tsx`
- Modify: `shared/lichtblick-robot-control/src/styles.css`

- [x] Place the map-name input and mapping action in one grid row.
- [x] Switch between Start mapping and Finish mapping from live mapping state.
- [x] Lock the map-name input during mapping.
- [x] Remove the separate two-button action row.

### Task 2: Ship Robot Control 0.8.0

**Files:**
- Modify: `shared/lichtblick-robot-control/package.json`
- Modify: `shared/lichtblick-robot-control/package-lock.json`
- Modify: `shared/lichtblick-robot-control/CHANGELOG.md`
- Modify: `shared/lichtblick-robot-control/README.md`
- Modify: `robot-navigation/Makefile`
- Modify: `robot-navigation/docker/Dockerfile`
- Modify: `robot-navigation/README.md`

- [x] Bump the extension artifact to 0.8.0.
- [x] Update user-facing mapping workflow text.
- [x] Commit and push without staging saved maps.
