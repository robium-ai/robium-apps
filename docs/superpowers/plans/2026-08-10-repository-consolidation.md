# Robium Applications Repository Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `robium-apps` the sole applications repository, preserve every unique application artifact and improvement, reconcile indoor-navigation, update all active ownership references, then permanently delete the obsolete repository.

**Architecture:** Use the current public repository as the merge base. Copy only internal-only tracked content, semantically reconcile the divergent indoor-navigation application, then update the plugin and website repositories to resolve applications from `robium-apps`. Verification and pushes precede the isolated remote/local deletion task.

**Tech Stack:** Git, GitHub CLI, ROS 2 Jazzy, Nav2, Gazebo Harmonic, Pixi/RoboStack, Docker Compose, Python 3.12, Lichtblick/Foxglove bridge, Node.js validation scripts.

## Global Constraints

- `robium-apps` survives with its existing Git history; do not merge unrelated repository history or retain a Git bundle.
- Preserve the public mapping/localization dashboard as the indoor-navigation base.
- Remove the overhead camera model, spawn, bridge, topic, and panels everywhere.
- Keep only TurtleBot 3 `burger_cam` and `/camera/image_raw` for simulated imagery.
- Preserve both Docker/Cloud Run and native macOS arm64 Pixi/RoboStack execution.
- Do not copy generated environments, caches, logs, `.robium` state, transcripts, or worktree metadata.
- Recreate the native Pixi environment under the surviving public path because Conda prefixes embed absolute paths.
- Do not delete the obsolete GitHub repository or local checkout until every migration, verification, commit, and push gate passes.
- Use `/Users/mdemirst/repos/robium-internal-apps` only as the explicit source; never broaden a destructive target.
- Remove this temporary plan and its paired design specification during final stale-reference cleanup.

---

### Task 1: Capture the source inventory and migrate internal-only content

**Files:**
- Create: `/Users/mdemirst/repos/robium-apps/quadruped-locomotion/**`
- Create: `/Users/mdemirst/repos/robium-apps/robot-teleoperation/**`
- Create: `/Users/mdemirst/repos/robium-apps/shared/demo-gateway/**`
- Create: `/Users/mdemirst/repos/robium-apps/.github/workflows/validate.yml`
- Create: `/Users/mdemirst/repos/robium-apps/docs/polish-playbook.md`
- Modify: `/Users/mdemirst/repos/robium-apps/README.md`
- Modify: `/Users/mdemirst/repos/robium-apps/REGISTRY.md`

**Interfaces:**
- Consumes: tracked files from the retiring repository and the approved inventory in the design specification.
- Produces: a public catalog containing every unique application/support artifact, with no ignored runtime state.

- [ ] **Step 1: Record clean destination and dirty source state**

Run:

```bash
git -C /Users/mdemirst/repos/robium-apps status --short
git -C /Users/mdemirst/repos/robium-internal-apps status --short
git -C /Users/mdemirst/repos/robium-internal-apps ls-files > /tmp/robium-internal-tracked-files.txt
```

Expected: public contains only the committed spec/plan work; source dirtiness is limited to the indoor-navigation and registry work already inventoried.

- [ ] **Step 2: Reconfirm identical surviving applications**

Run:

```bash
diff -qr --exclude=.robium /Users/mdemirst/repos/robium-internal-apps/imitation-manipulation /Users/mdemirst/repos/robium-apps/imitation-manipulation
diff -qr --exclude=.robium /Users/mdemirst/repos/robium-internal-apps/vla-language-learning /Users/mdemirst/repos/robium-apps/vla-language-learning
```

Expected: no output from either command.

- [ ] **Step 3: Copy tracked internal-only directories without ignored state**

Run from `/Users/mdemirst/repos/robium-internal-apps`:

```bash
git archive --format=tar HEAD quadruped-locomotion robot-teleoperation shared | tar -xf - -C /Users/mdemirst/repos/robium-apps
```

Then copy the workflow and playbook as explicit tracked files:

```bash
mkdir -p /Users/mdemirst/repos/robium-apps/.github/workflows /Users/mdemirst/repos/robium-apps/docs
cp -p .github/workflows/validate.yml /Users/mdemirst/repos/robium-apps/.github/workflows/validate.yml
cp -p docs/polish-playbook.md /Users/mdemirst/repos/robium-apps/docs/polish-playbook.md
```

Expected: only tracked source content appears; no `.robium`, cache, or runtime directories are introduced.

- [ ] **Step 4: Add canonical catalog entries**

Update `README.md` and `REGISTRY.md` with entries/cards for quadruped locomotion and robot teleoperation. Describe `shared/demo-gateway` as reusable support code rather than an application. Do not add the retired workspace flavor as an app.

- [ ] **Step 5: Run migrated-content checks**

Run:

```bash
git diff --check
make -C quadruped-locomotion check
make -C robot-teleoperation check
python3 -m unittest shared/demo-gateway/test_gateway.py
```

Expected: each command exits 0. If a hardware/cloud app's `check` target is static-only, record that limitation without claiming a hardware runtime pass.

- [ ] **Step 6: Commit migrated applications**

```bash
git add .github README.md REGISTRY.md docs/polish-playbook.md quadruped-locomotion robot-teleoperation shared
git commit -m "feat: consolidate remaining robotics applications"
```

---

### Task 2: Merge the native macOS runtime into public indoor-navigation

**Files:**
- Create: `/Users/mdemirst/repos/robium-apps/indoor-navigation/.gitignore`
- Create: `/Users/mdemirst/repos/robium-apps/indoor-navigation/experiments/native-macos/.gitignore`
- Create: `/Users/mdemirst/repos/robium-apps/indoor-navigation/experiments/native-macos/pixi.toml`
- Create: `/Users/mdemirst/repos/robium-apps/indoor-navigation/experiments/native-macos/pixi.lock`
- Create: `/Users/mdemirst/repos/robium-apps/indoor-navigation/scripts/native_paths.py`
- Create: `/Users/mdemirst/repos/robium-apps/indoor-navigation/scripts/native_setup.py`
- Create: `/Users/mdemirst/repos/robium-apps/indoor-navigation/scripts/native_demo.py`
- Create: `/Users/mdemirst/repos/robium-apps/indoor-navigation/tests/test_native_paths.py`
- Create: `/Users/mdemirst/repos/robium-apps/indoor-navigation/tests/test_native_setup.py`
- Create: `/Users/mdemirst/repos/robium-apps/indoor-navigation/tests/test_native_demo.py`
- Modify: `/Users/mdemirst/repos/robium-apps/indoor-navigation/Makefile`
- Modify: `/Users/mdemirst/repos/robium-apps/indoor-navigation/README.md`
- Modify: `/Users/mdemirst/repos/robium-apps/indoor-navigation/docs/architecture-brief.md`

**Interfaces:**
- Consumes: the verified internal native scripts, manifest, lock, and tests.
- Produces: `make native-setup`, `make demo-native`, and `make native-down` rooted entirely under the public app.

- [ ] **Step 1: Copy only portable native source/config files**

Run:

```bash
source_app=/Users/mdemirst/repos/robium-internal-apps/indoor-navigation
public_app=/Users/mdemirst/repos/robium-apps/indoor-navigation
mkdir -p "$public_app/experiments/native-macos"
cp -p "$source_app/.gitignore" "$public_app/.gitignore"
cp -p "$source_app/experiments/native-macos/.gitignore" "$public_app/experiments/native-macos/.gitignore"
cp -p "$source_app/experiments/native-macos/pixi.toml" "$public_app/experiments/native-macos/pixi.toml"
cp -p "$source_app/experiments/native-macos/pixi.lock" "$public_app/experiments/native-macos/pixi.lock"
cp -p "$source_app/scripts/native_paths.py" "$public_app/scripts/native_paths.py"
cp -p "$source_app/scripts/native_setup.py" "$public_app/scripts/native_setup.py"
cp -p "$source_app/scripts/native_demo.py" "$public_app/scripts/native_demo.py"
cp -p "$source_app/tests/test_native_paths.py" "$public_app/tests/test_native_paths.py"
cp -p "$source_app/tests/test_native_setup.py" "$public_app/tests/test_native_setup.py"
cp -p "$source_app/tests/test_native_demo.py" "$public_app/tests/test_native_demo.py"
```

Do not copy `.pixi`, `runtime`, `build`, `install`, or `log`.

- [ ] **Step 2: Merge Makefile targets and documentation**

Add native targets to the public Makefile without removing its mapping targets. Merge native setup/run instructions into the public README and architecture brief while retaining the public dashboard, mapping/localization, and Docker documentation.

- [ ] **Step 3: Verify public-root path derivation**

Run:

```bash
cd /Users/mdemirst/repos/robium-apps/indoor-navigation
python3 scripts/native_demo.py --help
python3 -m unittest tests.test_native_paths tests.test_native_setup tests.test_native_demo
```

Expected: direct invocation succeeds and all native orchestration tests pass without referencing the old absolute repository path.

- [ ] **Step 4: Commit the portable native runtime**

```bash
git add indoor-navigation/.gitignore indoor-navigation/experiments indoor-navigation/scripts/native_*.py indoor-navigation/tests/test_native_*.py indoor-navigation/Makefile indoor-navigation/README.md indoor-navigation/docs/architecture-brief.md
git commit -m "feat: add isolated native macOS navigation runtime"
```

---

### Task 3: Fix the native `/scan` discovery race with a regression test

**Files:**
- Modify: `/Users/mdemirst/repos/robium-apps/indoor-navigation/scripts/native_demo.py`
- Modify: `/Users/mdemirst/repos/robium-apps/indoor-navigation/tests/test_native_demo.py`

**Interfaces:**
- Consumes: `NativePaths`, `native_environment`, the launched process, renderer-failure event, and a 45-second deadline.
- Produces: `wait_for_scan(paths: NativePaths, process: subprocess.Popen, renderer_failed: threading.Event, deadline: float) -> None`.

- [ ] **Step 1: Add the failing discovery-race test**

Create a test that mocks the scan probe sequence as:

1. return code 1 with stderr `Could not determine the type for the passed topic`;
2. return code 0 with a LaserScan payload containing `ranges:\n- 1.0`.

Assert `wait_for_scan` retries and returns without stopping the process.

The test shape is:

```python
@mock.patch('scripts.native_demo.subprocess.run')
def test_scan_wait_retries_transient_type_discovery(self, run):
    from scripts.native_demo import wait_for_scan
    run.side_effect = [
        subprocess.CompletedProcess([], 1, '',
                                    'Could not determine the type for the passed topic'),
        subprocess.CompletedProcess([], 0, 'ranges:\n- 1.0\n', ''),
    ]
    process = mock.Mock()
    process.poll.return_value = None
    wait_for_scan(self.paths, process, threading.Event(), time.monotonic() + 1)
    self.assertEqual(run.call_count, 2)
```

- [ ] **Step 2: Run the focused test and confirm failure**

```bash
python3 -m unittest tests.test_native_demo.NativeDemoTests.test_scan_wait_retries_transient_type_discovery
```

Expected: failure because `wait_for_scan` does not exist or the current one-shot implementation raises immediately.

- [ ] **Step 3: Implement condition-based scan readiness**

Implement `wait_for_scan` so each probe has a short bounded timeout, transient nonzero results retry until the shared deadline, process exit and renderer failure abort immediately, and the timeout error includes the last probe detail. Replace `_require_scan(paths)` in `run_demo` with the new function.

Use this control flow:

```python
def wait_for_scan(paths, process, renderer_failed, deadline):
    last_detail = 'topic not discovered'
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise NativeError(f'native ROS launch exited during scan readiness ({process.returncode})')
        if renderer_failed.is_set():
            raise NativeError('Gazebo renderer initialization failed')
        try:
            result = subprocess.run(
                scan_health_command(paths), cwd=paths.app_root,
                env=native_environment(paths), capture_output=True, text=True,
                timeout=min(5.0, max(0.1, deadline - time.monotonic())),
                check=False)
        except subprocess.TimeoutExpired:
            last_detail = 'scan probe timed out'
            continue
        compact = result.stdout.replace(' ', '')
        if result.returncode == 0 and 'ranges:\n-' in compact:
            return
        last_detail = (result.stderr or result.stdout).strip()[-500:]
        time.sleep(0.25)
    raise NativeError(f'/scan did not publish within 45 seconds: {last_detail}')
```

- [ ] **Step 4: Run native orchestration tests**

```bash
python3 -m unittest tests.test_native_demo
```

Expected: all tests pass, including the transient discovery regression.

- [ ] **Step 5: Commit the race fix**

```bash
git add indoor-navigation/scripts/native_demo.py indoor-navigation/tests/test_native_demo.py
git commit -m "fix: wait for native scan topic discovery"
```

---

### Task 4: Reconcile indoor-navigation ROS, Gazebo, Docker, and dashboard behavior

**Files:**
- Modify: `/Users/mdemirst/repos/robium-apps/indoor-navigation/docker/Dockerfile`
- Modify: `/Users/mdemirst/repos/robium-apps/indoor-navigation/docker/compose.yaml`
- Modify: `/Users/mdemirst/repos/robium-apps/indoor-navigation/lichtblick/nav-layout.json`
- Modify: `/Users/mdemirst/repos/robium-apps/indoor-navigation/lichtblick/mapping-layout.json`
- Modify: `/Users/mdemirst/repos/robium-apps/indoor-navigation/foxglove/indoor-navigation-layout.json`
- Modify: `/Users/mdemirst/repos/robium-apps/indoor-navigation/scripts/demo_gateway.py`
- Modify: `/Users/mdemirst/repos/robium-apps/indoor-navigation/src/indoor_nav_bringup/launch/sim.launch.py`
- Modify: `/Users/mdemirst/repos/robium-apps/indoor-navigation/src/indoor_nav_bringup/launch/demo.launch.py`
- Modify: `/Users/mdemirst/repos/robium-apps/indoor-navigation/src/indoor_nav_bringup/launch/nav.launch.py`
- Modify: `/Users/mdemirst/repos/robium-apps/indoor-navigation/src/indoor_nav_bringup/launch/mapping.launch.py`
- Modify: `/Users/mdemirst/repos/robium-apps/indoor-navigation/src/indoor_nav_bringup/maps/map.pgm`
- Modify: `/Users/mdemirst/repos/robium-apps/indoor-navigation/src/indoor_nav_bringup/maps/map.yaml`
- Delete: `/Users/mdemirst/repos/robium-apps/indoor-navigation/src/indoor_nav_bringup/models/overhead_camera/**`
- Modify: related indoor-navigation tests and documentation.

**Interfaces:**
- Consumes: public mapping services/relay and internal verified native house scenario, viewer patch, map, goals, and camera optimization.
- Produces: one scenario contract shared by Docker and native modes, with service controls and robot camera but no overhead camera.

- [ ] **Step 1: Add or update structural assertions**

Tests must assert:

- `TURTLEBOT3_MODEL=burger_cam` in native and Docker paths;
- every layout contains `Image!robotcam` on `/camera/image_raw`;
- mapping layout retains `Indicator!state`, `Teleop!drive`, and `CallService!save/load/reset`;
- no source/layout contains `overhead_camera`, `/overhead/image_raw`, or `Image!overhead`;
- the house world, map dimensions/origin, spawn, initial pose, and goal constants agree;
- the Docker and native viewer installers both apply the guarded publisher-cleanup rewrite;
- both environments guard-convert the stock burger camera to the same lightweight 10 Hz pinhole configuration.

- [ ] **Step 2: Run the focused structural suite and observe failures**

```bash
python3 -m unittest tests.test_demo_portability tests.test_house_scenario tests.test_launch_modes tests.test_native_setup
```

Expected: failures identify the public/internal behavior not yet reconciled.

- [ ] **Step 3: Remove overhead-camera implementation**

Delete the tracked overhead model directory. Remove its launch spawn, bridge, topic, Docker copy/build wiring, and dashboard panel. Keep the upstream `burger_cam` image bridge and robot panel.

- [ ] **Step 4: Merge the verified house scenario and publisher fix**

Reconcile the public mapping stack with the internal house map/spawn/goals. Apply the publisher-cleanup guard to both Docker and native viewer installation. Preserve the public mapping services, teleop relay, mapping/localization mode split, and request-time mapping layout server.

- [ ] **Step 5: Make camera behavior identical in Docker and native modes**

Select `burger_cam` in compose/native environments. Guard-convert exactly one stock camera sensor from wide-angle 30 Hz to pinhole 10 Hz with horizontal FOV 1.5 and no lens block. Fail setup/build if the upstream model shape drifts instead of silently rewriting an unknown file.

- [ ] **Step 6: Rebuild the three layouts**

Navigation/demo layout: 3D navigation state plus robot camera and goal diagnostics. Mapping layout: 3D state, mapping indicator, teleop, save/load/reset, map-name parameter, available maps, and robot camera. External Foxglove layout mirrors navigation topics and `/goal_pose` publishing. No layout contains overhead imagery.

- [ ] **Step 7: Run structural and package checks**

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
jq empty lichtblick/nav-layout.json lichtblick/mapping-layout.json foxglove/indoor-navigation-layout.json
git diff --check
```

Expected: all tests and parsers pass.

- [ ] **Step 8: Commit the consolidated indoor-navigation app**

```bash
git add indoor-navigation
git commit -m "feat: unify navigation dashboard and native simulation"
```

---

### Task 5: Recreate and verify indoor-navigation from the public path

**Files:**
- Generated only: `/Users/mdemirst/repos/robium-apps/indoor-navigation/experiments/native-macos/{.pixi,runtime,build,install,log}`
- Verification logs only; no generated state is staged.

**Interfaces:**
- Consumes: Tasks 2–4.
- Produces: runtime evidence for Docker, mapping/localization controls, native Metal Gazebo, robot camera, and clicked navigation.

- [ ] **Step 1: Stop the old owned native demo**

```bash
make -C /Users/mdemirst/repos/robium-internal-apps/indoor-navigation native-down
```

Expected: `native demo stopped` or `no owned native demo is running`.

- [ ] **Step 2: Install a fresh public native environment**

```bash
make -C /Users/mdemirst/repos/robium-apps/indoor-navigation native-setup
```

Expected: install succeeds entirely beneath the public app and leaves the Git worktree unchanged.

- [ ] **Step 3: Verify native runtime**

Run `make demo-native`, wait for the readiness message, then verify:

```bash
ros2 topic info -v /scan
ros2 topic echo --once /camera/image_raw --field header
ros2 topic list | rg '^/overhead' && exit 1 || true
```

Using the app's Pixi shell/environment, verify a clicked Lichtblick `/goal_pose` reaches Nav2 and the robot camera panel renders a live house frame. Confirm the Gazebo log selects the Apple Metal renderer.

- [ ] **Step 4: Verify Docker and mapping dashboard**

```bash
make build
make smoke
make demo-smoke
```

Start the mapping profile and confirm the service list includes `/mapping/save`, `/mapping/reset`, and the mode-correct `/mapping/load` wrapper; verify the state, teleop, maps, and camera panels receive data. Run the existing bounded mapping checks without overwriting the canonical map unless the test uses a temporary map name.

- [ ] **Step 5: Confirm generated state is ignored**

```bash
git status --short
git check-ignore -v indoor-navigation/experiments/native-macos/.pixi indoor-navigation/experiments/native-macos/runtime
```

Expected: generated paths do not appear as untracked content.

---

### Task 6: Rewrite repository ownership and all active references

**Files:**
- Modify: `/Users/mdemirst/repos/robium/AGENTS.md`
- Modify: `/Users/mdemirst/repos/robium/.claude/hooks/session-start.sh`
- Modify: matching tracked plans/specs/learnings under `/Users/mdemirst/repos/robium/`
- Modify: `/Users/mdemirst/repos/robium-apps/AGENTS.md`
- Modify: `/Users/mdemirst/repos/robium-apps/README.md`
- Modify: `/Users/mdemirst/repos/robium-apps/REGISTRY.md`
- Modify: `/Users/mdemirst/repos/robium-apps/docs/reference-applications-design.md`
- Modify: `/Users/mdemirst/repos/robium-website/AGENTS.md`
- Modify: `/Users/mdemirst/repos/robium-website/.claude/settings.json`
- Modify: `/Users/mdemirst/repos/robium-website/demo-orchestrator/scripts/sync-demos.mjs`
- Modify: `/Users/mdemirst/repos/robium-website/scripts/fetch-apps.mjs`
- Modify: `/Users/mdemirst/repos/robium-website/scripts/fetch-articles.mjs`
- Modify: `/Users/mdemirst/repos/robium-website/tests/smoke.sh`
- Modify: matching tracked plans/specs under `/Users/mdemirst/repos/robium-website/`

**Interfaces:**
- Consumes: the consolidated public catalog and its app contracts.
- Produces: one ownership model and sibling checkout default, `../robium-apps`.

- [ ] **Step 1: Rewrite active guidance**

Make `robium-apps` the build/proving/reference/public repository. Keep app-scoped learnings in `robium/learnings`. Remove the private-to-public promotion workflow and update site/backend ownership accordingly.

- [ ] **Step 2: Rewrite executable paths and defaults**

Change website fetchers, article loaders, demo synchronizers, workspace settings, and local-path examples from the retired sibling to `../robium-apps`. Keep the `ROBIUM_APPS_DIR` override intact.

- [ ] **Step 3: Rewrite historical tracked references that remain live documentation**

Update repository URLs, clone commands, issue references, source labels, and ownership statements. Do not mechanically replace unrelated uses of “internal.” Remove obsolete historical claims that only document the old split when rewriting them would be misleading.

- [ ] **Step 4: Run repository-specific checks**

```bash
git -C /Users/mdemirst/repos/robium diff --check
git -C /Users/mdemirst/repos/robium-apps diff --check
git -C /Users/mdemirst/repos/robium-website diff --check
```

Run the robium manifest sanity command, the public validation workflow's local commands, website unit/smoke checks that do not deploy, and the demo sync/fetch scripts against `/Users/mdemirst/repos/robium-apps`.

- [ ] **Step 5: Commit each repository independently**

Use scoped commits:

```bash
git -C /Users/mdemirst/repos/robium add AGENTS.md .claude docs learnings
git -C /Users/mdemirst/repos/robium commit -m "docs: make robium-apps the application source"

git -C /Users/mdemirst/repos/robium-website add AGENTS.md .claude demo-orchestrator scripts tests docs
git -C /Users/mdemirst/repos/robium-website commit -m "chore: source demos from robium-apps"

git -C /Users/mdemirst/repos/robium-apps add AGENTS.md README.md REGISTRY.md docs
git -C /Users/mdemirst/repos/robium-apps commit -m "docs: unify application development and publishing"
```

---

### Task 7: Audit completeness and remove temporary migration documents

**Files:**
- Delete: `/Users/mdemirst/repos/robium-apps/docs/superpowers/specs/2026-08-10-repository-consolidation-design.md`
- Delete: `/Users/mdemirst/repos/robium-apps/docs/superpowers/plans/2026-08-10-repository-consolidation.md`
- Update: dated app/repository learning and end-of-block retro in `/Users/mdemirst/repos/robium/learnings/`.

**Interfaces:**
- Consumes: all migrated and rewritten trees.
- Produces: deletion-gate evidence with zero stale tracked references.

- [ ] **Step 1: Classify every tracked source file**

Compare `/tmp/robium-internal-tracked-files.txt` against the disposition categories in the design. Verify identical apps, migrated directories, semantically merged indoor-navigation, retired workspace duplicate, folded root metadata, and intentionally discarded old catalog/agent files. Stop if any path lacks a category.

- [ ] **Step 2: Run the final stale-reference search before removing migration docs**

Search tracked files in all three surviving repositories for:

```text
robium-internal-apps
internal-apps
private proving ground
promotion from the private repository
```

Only the temporary spec/plan may still match.

- [ ] **Step 3: Remove temporary migration documents and capture learnings**

Delete the spec and plan, append the consolidation finding/retro to the appropriate dated learning file, and ensure that learning uses the surviving repository name without preserving a stale operational dependency.

- [ ] **Step 4: Run final current-tree audits**

```bash
git -C /Users/mdemirst/repos/robium grep -n -i -E 'robium-internal-apps|internal[- ]apps|private proving ground' && exit 1 || true
git -C /Users/mdemirst/repos/robium-apps grep -n -i -E 'robium-internal-apps|internal[- ]apps|private proving ground' && exit 1 || true
git -C /Users/mdemirst/repos/robium-website grep -n -i -E 'robium-internal-apps|internal[- ]apps|private proving ground' && exit 1 || true
```

Then rerun the full checks from Tasks 1, 4, 5, and 6 and confirm all three surviving worktrees contain only intentional committed changes.

- [ ] **Step 5: Commit the completed migration audit**

Commit removal of migration docs and any final learning/reference corrections in their owning repositories.

---

### Task 8: Push surviving repositories and permanently delete the obsolete repository

**Files:**
- Remote state: `robium-ai/robium-apps`, `robium-ai/robium`, `robium-ai/robium-website`, and the retiring GitHub repository.
- Local state: `/Users/mdemirst/repos/robium-internal-apps`.

**Interfaces:**
- Consumes: clean, verified, committed surviving repositories and explicit user authorization to delete the obsolete GitHub repository.
- Produces: pushed surviving repositories, absent obsolete remote, and no local checkout at the old path.

- [ ] **Step 1: Confirm push targets and clean worktrees**

```bash
git -C /Users/mdemirst/repos/robium status --short
git -C /Users/mdemirst/repos/robium-apps status --short
git -C /Users/mdemirst/repos/robium-website status --short
git -C /Users/mdemirst/repos/robium remote -v
git -C /Users/mdemirst/repos/robium-apps remote -v
git -C /Users/mdemirst/repos/robium-website remote -v
```

Expected: clean worktrees and remotes under `robium-ai`.

- [ ] **Step 2: Push reviewed surviving branches**

Push the intended branches for all three repositories. If repository policy requires pull requests or human merge, stop at that gate and do not delete the old remote until the changes are present on the surviving default branches.

- [ ] **Step 3: Verify surviving default branches contain the migration**

Use GitHub/API lookups to confirm the new apps, ownership guidance, and website path changes exist remotely. Re-run the stale-reference search on checked-out default branches if merges occurred remotely.

- [ ] **Step 4: Delete the obsolete GitHub repository**

Run only after Steps 1–3 pass:

```bash
gh repo delete robium-ai/robium-internal-apps --yes
```

Expected: command exits 0. Then `gh repo view robium-ai/robium-internal-apps` must fail with not found.

- [ ] **Step 5: Remove the local checkout recoverably**

Confirm the exact source path, stop any remaining owned processes, and move the checkout to an explicit Trash target:

```bash
mv /Users/mdemirst/repos/robium-internal-apps /Users/mdemirst/.Trash/robium-internal-apps-2026-08-10
```

Expected: `/Users/mdemirst/repos/robium-internal-apps` no longer exists. Report that the local copy remains recoverable from Trash until emptied, while the GitHub deletion is permanent.

- [ ] **Step 6: Final completion verification**

Confirm all surviving repository remotes/default branches, current-tree stale-reference audits, local-path absence, and GitHub not-found result. Only then mark the consolidation complete.
