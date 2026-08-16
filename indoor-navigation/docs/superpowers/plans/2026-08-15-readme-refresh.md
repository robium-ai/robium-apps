# Indoor Navigation README Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the indoor-navigation README as a compact run guide for robotics developers.

**Architecture:** Keep the main path linear: understand the app, run it, use the dashboard, then inspect deeper details. Move native setup, reuse, and deployment after the primary Docker workflow.

**Tech Stack:** Markdown, Docker Compose, Make, ROS 2 Jazzy, Nav2, Gazebo Harmonic, Lichtblick

## Global Constraints

- Use short, direct technical language.
- Do not use em dashes.
- Keep the README compact and remove repeated explanations.
- Add text placeholders only for the future hero image and demo GIF.
- Do not create or run automated tests.

---

### Task 1: Rewrite and review the README

**Files:**
- Modify: `indoor-navigation/README.md`

**Interfaces:**
- Consumes: lifecycle commands from `indoor-navigation/Makefile`, app metadata from `indoor-navigation/robium-app.yaml`, and reusable panel guidance from `shared/lichtblick-dashboard/README.md`
- Produces: the primary clone, run, operate, and troubleshoot guide for indoor-navigation

- [x] **Step 1: Replace the accumulated README structure**

Lead with the outcome and media placeholders, put the Docker quick start first,
and group the dashboard workflow into mapping, localization, waypoints,
movement, visualization, and simulation.

- [x] **Step 2: Keep secondary material short**

Summarize data storage, shared assets, architecture, Dashboard reuse, native
macOS, external viewers, and maintainer deployment. Link to focused docs for
details.

- [x] **Step 3: Review the document without running tests**

Run bounded text checks for headings, em dashes, stale names, and whitespace.
Read the final document once for repetition and unnatural phrasing.
