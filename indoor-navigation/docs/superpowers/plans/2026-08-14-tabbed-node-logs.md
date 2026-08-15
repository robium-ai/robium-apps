# Tabbed Node Logs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single dashboard log view with All, Navigation, and Mapping & App tabs.

**Architecture:** Use Lichtblick's built-in `Tab` panel as the lower-left layout node. Give each tab its own `RosOut` child configuration on `/rosout`; use search terms to filter the two grouped views by node name.

**Tech Stack:** Lichtblick layout JSON, ROS 2 `/rosout`

## Global Constraints

- Preserve the existing Camera, 3D, and Robot Control layout and split percentages.
- Keep All active by default and show INFO-and-higher logs in every tab.
- Do not add or run automated tests.
- Do not rebuild the Docker image or Robot Control extension.

---

### Task 1: Configure the tabbed log region

**Files:**
- Modify: `indoor-navigation/lichtblick/mapping-layout.json`
- Modify: `indoor-navigation/README.md`

**Interfaces:**
- Consumes: Lichtblick `Tab` layout configuration and `RosOut` panel configuration.
- Produces: `Tab!logs` with `RosOut!logs-all`, `RosOut!logs-navigation`, and `RosOut!logs-mapping-app` children.

- [ ] **Step 1: Replace the single log configuration**

Add a `Tab!logs` config with titles `All`, `Navigation`, and `Mapping & App`.
Configure the All child with no search terms, the Navigation child with the
approved Nav2/localization node terms, and the Mapping & App child with
`slam_toolbox`, `session_manager`, and `teleop_relay`.

- [ ] **Step 2: Put the Tab panel in the existing lower-left slot**

Replace only the lower-left layout leaf `RosOut!logs` with `Tab!logs`. Preserve
the 36%, 72%, and 76% splits.

- [ ] **Step 3: Document the log tabs**

Update the default-control-panel section to name the three tabs and explain
that the grouped tabs filter `/rosout` by node.

- [ ] **Step 4: Review the diff and commit**

Review only the two intended runtime/documentation files, keep saved maps
untracked, commit, and push the existing promotion branch.

