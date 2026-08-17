# Robot Navigation Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Rename the active navigation reference app to `robot-navigation`, make the Robium CLI its primary documented lifecycle, and publish the renamed article and assets under a stable new URL.

**Architecture:** The app manifest remains the contract shared by the application, CLI, and website. Rename the app and ROS package first, update current consumers second, then regenerate the website from the canonical case study and retain only two explicit compatibility redirects for the former public URLs.

**Tech Stack:** ROS 2 Jazzy, Nav2, Gazebo Harmonic, Docker Compose v2, Node.js `robium-ai` CLI, Astro 6, Markdown.

## Global Constraints

- The public app name is **Robot Navigation**; the stable app ID is `robot-navigation`.
- The shared GitHub repository remains `robium-ai/robium-apps`.
- Active ROS package and Python module names become `robot_nav_bringup`.
- Historical plans, specifications, changelog entries, Git history, and dated learning records retain their original wording.
- The former product name may remain only in historical records and the two explicit compatibility redirects.
- Preserve local saved maps, waypoint sidecars, `.robium` session data, and all unrelated worktree changes.
- Do not stage `.DS_Store`, local maps, waypoint sidecars, caches, or backup media.
- Do not run unit or smoke tests. Focused command checks, application builds, and website builds are allowed.
- Do not commit, push, publish the npm package, or deploy the website unless separately requested.

---

### Task 1: Preserve local data and rename the application boundary

**Files:**
- Rename: `robot-navigation/` to `robot-navigation/`
- Rename: `/Users/mdemirst/repos/robium-backup/robot-navigation/` to `/Users/mdemirst/repos/robium-backup/robot-navigation/`
- Preserve: `robot-navigation/data/maps/**`
- Preserve: `robot-navigation/src/robot_nav_bringup/maps/**` until the ROS package directory moves

**Interfaces:**
- Consumes: the existing app directory and local media backup.
- Produces: the new application root `robot-navigation/` used by every later task.

- [x] **Step 1: Inventory local-only data before moving**

Run:

```bash
find robot-navigation/data/maps robot-navigation/src/robot_nav_bringup/maps -maxdepth 3 -type f -print 2>/dev/null | sort
find /Users/mdemirst/repos/robium-backup/robot-navigation -type f -print 2>/dev/null | wc -l
git status --short
```

Expected: saved maps and sidecars are visible but remain untracked or ignored; the backup contains 90 raw PNG frames.

- [x] **Step 2: Move the app and backup with explicit paths**

Run:

```bash
mv /Users/mdemirst/repos/robium-apps/robot-navigation /Users/mdemirst/repos/robium-apps/robot-navigation
mv /Users/mdemirst/repos/robium-backup/robot-navigation /Users/mdemirst/repos/robium-backup/robot-navigation
```

Expected: neither old directory exists and both new directories do.

- [x] **Step 3: Verify preservation immediately**

Run:

```bash
find robot-navigation/data/maps robot-navigation/src/robot_nav_bringup/maps -maxdepth 3 -type f -print 2>/dev/null | sort
find /Users/mdemirst/repos/robium-backup/robot-navigation/raw -type f -name '*.png' | wc -l
```

Expected: the pre-move local map listing is preserved and the backup count is `90`.

### Task 2: Rename the ROS package and application runtime identifiers

**Files:**
- Rename: `robot-navigation/src/robot_nav_bringup/` to `robot-navigation/src/robot_nav_bringup/`
- Rename: `robot-navigation/src/robot_nav_bringup/robot_nav_bringup/` to `robot-navigation/src/robot_nav_bringup/robot_nav_bringup/`
- Rename: `robot-navigation/src/robot_nav_bringup/resource/robot_nav_bringup` to `robot-navigation/src/robot_nav_bringup/resource/robot_nav_bringup`
- Rename: `robot-navigation/foxglove/robot-navigation-layout.json` to `robot-navigation/foxglove/robot-navigation-layout.json`
- Modify: active files below `robot-navigation/src/robot_nav_bringup/`
- Modify: `robot-navigation/scripts/native_demo.py`
- Modify: `robot-navigation/scripts/run_slam.sh`
- Modify: `robot-navigation/experiments/native-macos/pixi.toml`

**Interfaces:**
- Consumes: ROS package name `robot_nav_bringup` and app identifiers under the renamed app root.
- Produces: ROS package `robot_nav_bringup`, Python module `robot_nav_bringup`, and console entry points targeting that module.

- [x] **Step 1: Rename package directories and resource marker**

Run explicit `mv` commands for the three paths listed above and rename the Foxglove layout file.

Expected: package discovery paths contain `robot_nav_bringup` at all three levels.

- [x] **Step 2: Replace active package identifiers**

In the renamed package, scripts, and native Pixi manifest, replace:

```text
robot_nav_bringup -> robot_nav_bringup
robot-navigation  -> robot-navigation
Robot Navigation -> Robot Navigation
Robot Navigation -> Robot Navigation
```

Do not modify files under `docs/superpowers/` or `.robium/transcripts/`.

- [x] **Step 3: Check ROS package coherence**

Run:

```bash
rg -n 'robot_nav_bringup|robot-navigation|Robot Navigation|Robot Navigation' \
  robot-navigation/src robot-navigation/scripts robot-navigation/experiments robot-navigation/foxglove
python3 -m py_compile robot-navigation/src/robot_nav_bringup/robot_nav_bringup/*.py \
  robot-navigation/src/robot_nav_bringup/launch/*.py
```

Expected: `rg` returns no active matches and Python compilation exits zero.

### Task 3: Rename the app manifest, Docker lifecycle, and operator commands

**Files:**
- Modify: `robot-navigation/robium-app.yaml`
- Modify: `robot-navigation/Makefile`
- Modify: `robot-navigation/docker/Dockerfile`
- Modify: `robot-navigation/docker/Dockerfile.dockerignore`
- Modify: `robot-navigation/docker/compose.yaml`
- Modify: `robot-navigation/cloudbuild.yaml`
- Modify: `robot-navigation/README.md`
- Modify: `robot-navigation/docs/architecture-brief.md`

**Interfaces:**
- Consumes: app root `robot-navigation` and ROS package `robot_nav_bringup`.
- Produces: manifest ID `robot-navigation`, image `robot-navigation:latest`, and Make commands invoked by the Robium CLI.

- [x] **Step 1: Update the manifest contract**

Set the active identity and commands to:

```yaml
id: robot-navigation
name: Robot Navigation (TurtleBot 3 + Nav2)
```

Use `robot-navigation:latest` for the local image and `robot_nav_bringup` for the demo launch command. Keep `demo_id: nav-trial` unchanged.

- [x] **Step 2: Update Make and Docker paths**

Change the Make help/status labels, CLI examples, image inspection, Cloud Build path, Docker build context, image name, volume paths, comments, and every `ros2 launch` package argument to the new identifiers.

The lifecycle mapping must remain:

```text
robium app help robot-navigation   -> make help
robium app doctor robot-navigation -> make doctor
robium app build robot-navigation  -> make build
robium app run robot-navigation    -> make run
robium app status robot-navigation -> make status
robium app logs robot-navigation   -> make logs
robium app stop robot-navigation   -> make stop
```

- [x] **Step 3: Update current README and architecture paths**

Replace active clone, directory, package, Docker, CLI, and source-link references. Preserve factual history inside `docs/superpowers/` without editing it.

- [x] **Step 4: Validate active runtime text**

Run:

```bash
rg -n 'robot-navigation|robot_nav_bringup|Robot Navigation|Robot Navigation' \
  robot-navigation/robium-app.yaml robot-navigation/Makefile \
  robot-navigation/docker robot-navigation/cloudbuild.yaml \
  robot-navigation/README.md robot-navigation/docs/architecture-brief.md
docker compose -f robot-navigation/docker/compose.yaml config >/tmp/robot-navigation-compose.yaml
```

Expected: no former-name matches and Compose configuration renders successfully.

### Task 4: Update the applications registry and active cross-app consumers

**Files:**
- Modify: `REGISTRY.md`
- Modify: `README.md`
- Modify: `CONTRIBUTING.md`
- Modify: `docs/polish-playbook.md`
- Modify: `docs/reference-applications-design.md`
- Modify: `shared/demo-gateway/README.md`
- Modify: `vla-language-learning/src/vla_language_learning/demo/gateway.py`

**Interfaces:**
- Consumes: stable app ID and folder `robot-navigation`.
- Produces: repository discovery, registry links, and active cross-app configuration using the new ID.

- [x] **Step 1: Replace current catalog and bootstrap references**

Update links, tables, examples, allowed-app lists, and bootstrap-source references from the former app ID to `robot-navigation`. Do not rewrite historical plan files, including the imitation-manipulation rescope plan.

- [x] **Step 2: Confirm registry consistency**

Run:

```bash
rg -n 'robot-navigation|Robot Navigation|Robot Navigation' \
  REGISTRY.md README.md CONTRIBUTING.md docs/polish-playbook.md \
  docs/reference-applications-design.md shared/demo-gateway/README.md \
  vla-language-learning/src/vla_language_learning/demo/gateway.py
test -f robot-navigation/robium-app.yaml
```

Expected: no former-name matches and the registry link target exists.

### Task 5: Update the published CLI examples and fixtures

**Files:**
- Modify: `/Users/mdemirst/repos/robium/cli/README.md`
- Modify: `/Users/mdemirst/repos/robium/cli/test/apps.test.js`

**Interfaces:**
- Consumes: generic CLI implementation and manifest ID `robot-navigation`.
- Produces: published usage examples and fixture metadata that demonstrate the current app name.

- [x] **Step 1: Replace lifecycle and scaffold examples**

Use `robot-navigation` in `app describe`, `help`, `doctor`, `build`, `run`, `status`, `logs`, `stop`, and `app new --from` examples.

- [x] **Step 2: Update fixture IDs without running the unit suite**

Replace fixture app IDs, paths, and expected output strings in `cli/test/apps.test.js`. Do not alter generic CLI behavior.

- [x] **Step 3: Verify published command availability and local resolution**

Run:

```bash
npm exec --yes --package=robium-ai@0.6.0 -- robium app --help
node /Users/mdemirst/repos/robium/cli/bin/robium.js app help robot-navigation \
  --dir /Users/mdemirst/repos/robium-apps
node /Users/mdemirst/repos/robium/cli/bin/robium.js app doctor robot-navigation \
  --dir /Users/mdemirst/repos/robium-apps
```

Expected: published help lists lifecycle subcommands; local help shows the Make mapping; doctor resolves the renamed app.

### Task 6: Rewrite the canonical article lifecycle and maintenance sections

**Files:**
- Modify: `robot-navigation/docs/case-study.md`

**Interfaces:**
- Consumes: published `robium-ai@0.6.0`, app ID `robot-navigation`, and Make lifecycle commands.
- Produces: canonical article frontmatter `app: robot-navigation` and body copied by the website ingestion script.

- [x] **Step 1: Rename article identity and links**

Set `app: robot-navigation`. Replace the source, architecture, Dashboard-context, and repository-directory links with current URLs. Use Robot Navigation as the app name and do not describe it as indoor-only.

- [x] **Step 2: Add the system requirements section near the start**

State that the app is tested on macOS and Ubuntu, can run on an Ubuntu/Linux server, requires Git plus Docker with Compose v2 and a modern browser, needs no GPU or physical robot, and exposes the browser workspace on port `8080` with the ROS WebSocket bridge on `8765`.

- [x] **Step 3: Make the CLI the primary lifecycle path**

Document exactly:

```bash
npx robium-ai@latest setup
git clone https://github.com/robium-ai/robium-apps.git
cd robium-apps
npx robium-ai@latest app help robot-navigation
npx robium-ai@latest app doctor robot-navigation
npx robium-ai@latest app build robot-navigation
npx robium-ai@latest app run robot-navigation
```

Explain that `setup` installs Robium skills, the clone supplies the apps, and the CLI reads `robium-app.yaml` before invoking the corresponding Make command in the app directory.

- [x] **Step 4: Show direct Make alternatives and inspection commands**

Document:

```bash
cd robot-navigation
make help
make doctor
make build
make run
make status
make logs
make stop
```

Keep the explanation concise and show `status`, `logs`, and `stop` both in the lifecycle section and at the end where they are operationally useful.

- [x] **Step 5: Add the living-application closing**

Link to:

```text
https://github.com/robium-ai/robium-apps/tree/main/robot-navigation
https://github.com/robium-ai/robium-apps/issues
```

Say that the app is actively improved, invite readers to try it, and ask them to file reproducible bugs or improvement ideas.

- [x] **Step 6: Check current article language**

Run:

```bash
rg -n 'robot-navigation|Robot Navigation|Robot Navigation' robot-navigation/docs/case-study.md
rg -n 'robot-navigation|robium-ai@latest app|macOS|Ubuntu|issues' robot-navigation/docs/case-study.md
```

Expected: the former name is absent and every required new topic is present.

### Task 7: Generate the new website slug, assets, and compatibility redirects

**Files:**
- Modify: `/Users/mdemirst/repos/robium-website/astro.config.mjs`
- Modify: `/Users/mdemirst/repos/robium-website/nginx.conf`
- Modify: `/Users/mdemirst/repos/robium-website/scripts/fetch-articles.mjs`
- Generate: `/Users/mdemirst/repos/robium-website/src/data/articles/robot-navigation.md`
- Delete: `/Users/mdemirst/repos/robium-website/src/data/articles/robot-navigation.md`
- Generate: `/Users/mdemirst/repos/robium-website/public/articles/robot-navigation/**`
- Delete: `/Users/mdemirst/repos/robium-website/public/articles/robot-navigation/**`
- Generate: `/Users/mdemirst/repos/robium-website/src/data/apps.json`
- Modify: `/Users/mdemirst/repos/robium-website/demo-orchestrator/src/demos/nav-trial.json`
- Modify: `/Users/mdemirst/repos/robium-website/src/pages/demos/nav-trial.astro`
- Modify: `/Users/mdemirst/repos/robium-website/tests/smoke.sh`
- Modify: `/Users/mdemirst/repos/robium-website/docs/editorial/article-voice-standard.md`
- Modify: `/Users/mdemirst/repos/robium-website/docs/editorial/voice-reference-report.md`
- Modify: `/Users/mdemirst/repos/robium-website/docs/handover-2026-08-15.md`

**Interfaces:**
- Consumes: canonical article `app: robot-navigation`, app assets, and image `robot-navigation:latest`.
- Produces: canonical `/blog/robot-navigation/`, nested article assets, current demo references, and two permanent redirects.

- [x] **Step 1: Add only the two compatibility redirects**

Configure Astro permanent redirects:

```text
/blog/robot-navigation     -> /blog/robot-navigation
/articles/robot-navigation -> /blog/robot-navigation
```

Exclude both former paths from the sitemap filter. These are the only active website locations allowed to retain the former slug.

Mirror the same routes as exact `301` locations in `nginx.conf`. Astro's
static output supplies working redirects during local review, while nginx
supplies the production HTTP status code.

- [x] **Step 2: Update active website and demo references**

Use `robot-navigation:latest` in demo configuration and replace current app/article links and assertions. Historical website plans remain unchanged.

- [x] **Step 3: Regenerate article and app data**

Run from `robium-website`:

```bash
ROBIUM_APPS_DIR=/Users/mdemirst/repos/robium-apps \
ROBIUM_DIR=/Users/mdemirst/repos/robium \
npm run build
```

Expected: Astro builds `/blog/robot-navigation/`; ingestion copies GIFs and stills under `public/articles/robot-navigation/assets/`.

- [x] **Step 4: Remove stale generated fallback and assets**

After confirming the new generated files exist, delete only:

```text
src/data/articles/robot-navigation.md
public/articles/robot-navigation/
```

Run the website build again and confirm they are not regenerated.

- [x] **Step 5: Verify page and redirect output**

Run:

```bash
test -f dist/blog/robot-navigation/index.html
rg -n 'robot-navigation|Robot Navigation|robium-ai@latest' dist/blog/robot-navigation/index.html
test -f dist/blog/robot-navigation/index.html
test -f dist/articles/robot-navigation/index.html
rg -n 'robot-navigation' dist/blog/robot-navigation/index.html dist/articles/robot-navigation/index.html
```

Expected: the new article renders and both former paths are redirect pages pointing to it.

### Task 8: Build the renamed application and audit the completed rename

**Files:**
- Inspect: all changed active files in `robium-apps`, `robium`, and `robium-website`
- Preserve: historical documents, learning records, saved maps, and unrelated changes

**Interfaces:**
- Consumes: completed rename from Tasks 1–7.
- Produces: evidence that active application, CLI, and website surfaces agree on `robot-navigation`.

- [x] **Step 1: Build the renamed container**

Run:

```bash
cd /Users/mdemirst/repos/robium-apps/robot-navigation
make build
```

Expected: Docker produces `robot-navigation:latest` and the ROS workspace builds `robot_nav_bringup`.

- [x] **Step 2: Run lifecycle discovery checks**

Run:

```bash
cd /Users/mdemirst/repos/robium-apps
npx robium-ai@latest app list
npx robium-ai@latest app help robot-navigation
npx robium-ai@latest app doctor robot-navigation
```

Expected: the catalog lists `robot-navigation`, help maps to Make commands, and doctor completes its environment checks.

- [x] **Step 3: Audit active surfaces for former identifiers**

Run repository-specific `rg` searches excluding:

```text
docs/superpowers/**
learnings/**
archive/**
.robium/**
dist/**
node_modules/**
```

Expected: no former identifier appears in active app, CLI, or website files except the two Astro redirect entries.

- [x] **Step 4: Reconfirm local data and media**

Run:

```bash
find /Users/mdemirst/repos/robium-backup/robot-navigation/raw -type f -name '*.png' | wc -l
find /Users/mdemirst/repos/robium-apps/robot-navigation/data/maps -type f -print 2>/dev/null | sort
find /Users/mdemirst/repos/robium-apps/robot-navigation/src/robot_nav_bringup/maps -type f -print 2>/dev/null | sort
```

Expected: 90 backup frames and the pre-rename map files remain present.

- [x] **Step 5: Review diffs without committing**

Run `git diff --check`, `git status --short`, and focused diffs in all three repositories. Confirm `.DS_Store`, local maps, waypoint sidecars, caches, and unrelated maintainer changes are not staged or deleted.
