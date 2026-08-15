# Navigation Plan and Quick Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Show global and local navigation paths in distinct colors and remove Go Home from Robot Control.

**Architecture:** This is a presentation/configuration change. The committed Lichtblick layout renders Nav2's existing path topics, while the shared extension removes the unused Go Home interface and ships as version 0.6.0.

**Tech Stack:** JSON Lichtblick layout, TypeScript 5, React 18, Lichtblick extension SDK, CSS, Markdown.

## Global Constraints

- Do not add or run automated tests, lint, build, or smoke checks.
- Preserve Stop Robot's current behavior.
- Leave saved maps and waypoint sidecars untouched and untracked.

---

### Task 1: Display both Nav2 paths

**Files:**
- Modify: `indoor-navigation/lichtblick/mapping-layout.json`

- [ ] Keep `/plan` visible and change it to a thicker cyan line.
- [ ] Add visible `/local_plan` styling as an orange line.

### Task 2: Remove Go Home

**Files:**
- Modify: `shared/lichtblick-robot-control/src/RobotControlPanel.tsx`
- Modify: `shared/lichtblick-robot-control/src/lichtblickAdapter.ts`
- Modify: `shared/lichtblick-robot-control/src/panelConfig.ts`
- Modify: `shared/lichtblick-robot-control/src/styles.css`

- [ ] Remove the Go Home button and let Stop Robot occupy the full Quick Actions row.
- [ ] Narrow `callConfiguredService` to `navigationStopService`.
- [ ] Remove `goHomeService` from config defaults, parsing, and settings.

### Task 3: Ship the updated extension and docs

**Files:**
- Modify: `shared/lichtblick-robot-control/package.json`
- Modify: `shared/lichtblick-robot-control/package-lock.json`
- Modify: `shared/lichtblick-robot-control/CHANGELOG.md`
- Modify: `shared/lichtblick-robot-control/README.md`
- Modify: `indoor-navigation/Makefile`
- Modify: `indoor-navigation/docker/Dockerfile`
- Modify: `indoor-navigation/README.md`

- [ ] Bump Robot Control to `0.6.0` and update artifact paths.
- [ ] Document dual-color navigation paths and the single Stop Robot quick action.
- [ ] Commit the implementation without staging saved map directories.
