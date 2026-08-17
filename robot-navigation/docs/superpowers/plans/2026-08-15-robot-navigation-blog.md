# Robot Navigation Blog Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the old robot-navigation engineering story with an original tutorial-style blog post that matches the current application.

**Architecture:** Keep `docs/case-study.md` as the canonical portable Markdown source. Use frontmatter to classify it as a Blog tutorial now and to support topic filtering later.

**Tech Stack:** Markdown, ROS 2 Jazzy, Nav2, Gazebo Harmonic, slam_toolbox, Docker, Lichtblick

## Global Constraints

- Use direct technical language and natural paragraph lengths.
- Do not use em dashes.
- Use only commands and behavior present in the current application.
- Do not create or modify images or GIFs.
- Do not add or run automated tests.

---

### Task 1: Rewrite the canonical article

**Files:**
- Modify: `robot-navigation/docs/case-study.md`

**Interfaces:**
- Consumes: current commands from `robot-navigation/Makefile`, application behavior from `robot-navigation/README.md`, and frontmatter ingestion from `robium-website/scripts/fetch-articles.mjs`
- Produces: a portable Blog tutorial with category and tags for future website filtering

- [x] **Step 1: Replace the frontmatter**

Set the title, summary, tutorial kind and category, technical voice, current
date and tested date, app identifier, topic tags, existing hero, and featured
status.

- [x] **Step 2: Write the linear tutorial**

Cover prerequisites, startup, layout, mapping, localization, navigation,
waypoints, plans, logs, and the system model using current UI labels and Make
targets.

- [x] **Step 3: Preserve useful engineering evidence**

Include the `/cmd_vel` endpoint inspection, stamped velocity configuration,
and map-frame lesson as concise diagnostic sections instead of a chronological
failure memoir.

- [x] **Step 4: Review without tests**

Check frontmatter fields, commands, UI labels, local links, em dashes,
whitespace, and stale terms. Read the final article once for repetitive or
generic phrasing.
