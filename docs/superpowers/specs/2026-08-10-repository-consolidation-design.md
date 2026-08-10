# Robium Applications Repository Consolidation Design

**Date:** 2026-08-10

**Repositories:** `robium-apps`, `robium`, `robium-website`, and the retiring
`robium-internal-apps`

## Goal

Make `robium-ai/robium-apps` the only applications repository: development
workspace, proving ground, reference library, public showcase, and demo-backend
source. Migrate every unique tracked artifact from `robium-internal-apps`,
reconcile the divergent indoor-navigation implementations, update every active
reference to the surviving repository, then permanently delete the old GitHub
repository and remove its local checkout.

## Decisions

- `robium-apps` survives with its existing Git history. The unrelated
  `robium-internal-apps` history is not merged, bundled, or retained as an
  internal archive.
- The GitHub repository `robium-ai/robium-internal-apps` is permanently
  deleted only after all surviving-repository changes are verified and pushed.
- The local `robium-internal-apps` checkout is removed from its current path
  only after remote deletion succeeds. Prefer moving it to the macOS Trash so
  the local deletion remains temporarily recoverable.
- Generated environments, caches, logs, transcripts, queue files, and worktree
  metadata are not migrated. In particular, the 9.1 GB indoor-navigation Pixi
  runtime is recreated under the public checkout because Conda prefixes embed
  absolute paths.
- Existing application changes are reconciled semantically. The public app is
  never overwritten wholesale by an older internal copy.
- No overhead Gazebo camera remains in indoor-navigation. The only image feed
  is TurtleBot 3 `burger_cam` on `/camera/image_raw`.

## Inventory and disposition

### Already identical

The tracked application contents below compare identically between the two
repositories and require no content merge:

- `imitation-manipulation/`
- `vla-language-learning/`

Their surviving copies remain in `robium-apps`.

### Move into `robium-apps`

The following tracked content exists only in `robium-internal-apps` and moves
to the public repository:

- `quadruped-locomotion/`
- `robot-teleoperation/`
- `shared/demo-gateway/`
- `.github/workflows/validate.yml`
- `docs/polish-playbook.md`

Before migration, ignored runtime state and `.robium` capture artifacts are
excluded. Public-facing documentation and app contracts are checked for stale
private-repository language and secrets before being retained.

### Retire as a separate app

`indoor-navigation-workspace/` is an archived IDE-workspace flavor of the same
application. It does not survive as a separate directory. Any still-useful
behavior is represented by the consolidated main app or its documentation;
the obsolete duplicate is then removed with the rest of the internal checkout.

### Reconcile indoor-navigation

The public implementation is the base because it contains the newer interactive
mapping/localization dashboard. The internal implementation contributes the
native macOS runtime and fixes verified on 2026-08-10.

The result preserves:

- Docker and Cloud Run-compatible headless execution.
- Native macOS arm64 execution through app-local Pixi and RoboStack packages.
- Native Gazebo GUI using the Apple Metal renderer.
- TurtleBot 3 house world, matching occupancy map, spawn pose, initial pose,
  and verified navigation goals.
- Mapping and localization modes with mutually exclusive ROS node graphs.
- `map_manager` services `/mapping/save`, `/mapping/load`, and
  `/mapping/reset`.
- Mapping-state and available-map topics.
- Teleoperation through `/cmd_vel_teleop` and the ROS-side relay.
- Lichtblick click-to-navigate publication on `/goal_pose`, including the
  guarded bundle fix that prevents premature publisher cleanup.
- Robot-mounted `burger_cam`, upstream `ros_gz_image`, and
  `/camera/image_raw`.

The result removes:

- The overhead-camera SDF model.
- Its Gazebo spawn and image-bridge wiring.
- `/overhead/image_raw`.
- `Image!overhead` from every layout.

The mapping dashboard layout contains the 3D navigation state, mapping-state
indicator, teleop, save/load/reset controls, map-name parameter, available-map
view, and robot-camera panel. Navigation/demo layouts retain the 3D state,
goal publishing, and robot-camera panel without overhead imagery.

## Native startup reliability

The current native launcher has a reproducible discovery race. After the HTTP
gateway begins listening, it runs one `ros2 topic echo /scan --once`. If DDS
has not discovered `/scan`'s type yet, the command exits immediately with
`Could not determine the type for the passed topic`. The launcher treats that
transient result as final, sends SIGINT to the healthy ROS/Gazebo process group,
and reports a failed scan health check. Foxglove and Nav2 errors printed after
that point are shutdown fallout.

The consolidated launcher replaces the one-shot probe with a bounded,
condition-based readiness loop:

1. Keep the launched process and renderer under observation.
2. Poll ROS discovery until `/scan` has type `sensor_msgs/msg/LaserScan`.
3. Once typed, wait for one best-effort scan message containing non-empty
   ranges.
4. Retry transient discovery failures until the shared 45-second deadline.
5. Fail immediately if the launch process exits or the renderer reports a
   known fatal error.
6. On timeout, report the last discovery/message error before cleanly stopping
   the owned process group.

This behavior gets a regression test that reproduces an initial type-discovery
failure followed by a valid scan.

## Environment boundaries

Docker remains the portable and Cloud Run path. All ROS and Gazebo processes in
a scenario stay in one container so Docker Desktop does not have to route DDS
multicast between containers. The headless camera and GPU lidar continue to use
software rendering where no GPU is available.

The native path stays project-local:

- Manifest and lock: `indoor-navigation/experiments/native-macos/pixi.toml`
  and `pixi.lock`.
- Environment, cache, HOME, temporary files, logs, build, install, and viewer
  assets remain below `indoor-navigation/experiments/native-macos/`.
- Host secrets are filtered from child environments and build logs.
- No Homebrew package or system ROS installation is introduced.

The public checkout receives a fresh `make native-setup`; generated state from
the old absolute prefix is not copied.

## Repository ownership and references

`robium-apps/AGENTS.md` is rewritten so applications are built, hardened, and
published in one repository. It retains the two-hats learning rule: app work
uses robium skills like a client, while app-scoped learnings still land in
`robium/learnings/YYYY-MM-DD-<app>.md`. The old promotion workflow and
private-to-public distinction are removed.

The consolidation updates active ownership statements, local paths, clone
instructions, repository URLs, environment defaults, and demo-backend source
paths in:

- `robium/`
- `robium-apps/`
- `robium-website/`

This includes agent guidance, hooks, workspace settings, READMEs, registries,
design documents, implementation plans, learnings source labels, website
fetch/sync scripts, tests, and orchestrator defaults. Issue references that
point at `robium-internal-apps` are rewritten to the corresponding
`robium-apps` repository reference when they remain meaningful.

After migration, a tracked-file search across all three surviving repositories
must return no `robium-internal-apps`, `internal-apps`, private proving-ground,
or promotion-from-private ownership references. Generic prose using the word
“internal” for unrelated concepts is not changed.

This migration specification and its implementation plan necessarily name the
retiring repository. They are temporary execution artifacts and are removed
from the final tracked tree after their checklists and evidence have been
captured in the surviving repository's normal documentation and commit history.

## Public repository indexes

The `robium-apps` README and registry become the canonical catalog. They gain
entries/cards for the newly migrated applications and accurately describe the
consolidated indoor-navigation environment, visualization, and pass bar. The
retired workspace flavor is not listed as a separate application.

The internal README and registry are not migrated as competing catalogs. Their
unique app metadata is folded into the public catalog before the old checkout
is removed.

## Verification gates

### Migration completeness

- Produce a manifest of every tracked internal file and classify it as:
  identical, migrated, semantically merged, superseded, or intentionally
  retired.
- Confirm every internal-only application/support file marked migrated exists
  in `robium-apps` with matching content unless a documented rewrite was
  necessary.
- Confirm ignored `.robium`, cache, build, install, and runtime files were not
  added to Git.
- Run secret/PII scans before staging public content.

### Repository checks

- Validate JSON, YAML, Python syntax, shell syntax, and Git whitespace.
- Run the public repository validation workflow locally where supported.
- Run each migrated app's declared `make check` or equivalent bounded static
  gate.
- Run relevant automated tests for the consolidated indoor-navigation launch,
  mapping helpers, gateway, and native orchestration.

### Indoor-navigation runtime checks

- Docker image builds.
- Docker saved-map navigation reaches its declared goals.
- Mapping mode exposes `/mapping/save`, `/mapping/reset`, mapping state,
  teleop, and the robot image.
- Localization mode exposes `/mapping/load` and reaches a clicked Nav2 goal.
- Cloud Run-compatible demo gateway and Lichtblick bundle remain functional.
- Native setup completes under the public path.
- Native demo reaches readiness despite an initially undiscovered `/scan`.
- Native Gazebo opens the house world and selects Metal.
- `/scan` publishes non-empty ranges.
- `/camera/image_raw` publishes a real frame from `camera_rgb_frame` and
  Lichtblick renders it.
- `/goal_pose` retains a publisher and a clicked goal reaches Nav2.
- No `/overhead/*` topic, overhead model, bridge, or layout reference exists.

### Reference and deletion checks

- Tracked-file searches across `robium`, `robium-apps`, and `robium-website`
  find no stale internal-repository references.
- Website fetchers and demo synchronization resolve the sibling
  `../robium-apps` checkout by default.
- All changed surviving repositories have their intended commits pushed and
  clean worktrees before destructive deletion.
- `gh repo delete robium-ai/robium-internal-apps --yes` succeeds using an
  authenticated account with repository-deletion permission.
- A subsequent GitHub lookup reports the repository absent.
- The local checkout no longer exists at
  `/Users/mdemirst/repos/robium-internal-apps`.

## Failure handling

- If any internal tracked file lacks a disposition, stop before deletion.
- If public verification fails, retain the internal repository and local
  checkout until the failure is fixed and verification reruns.
- If a surviving repository cannot be pushed, do not delete the internal
  remote.
- If GitHub deletion authorization is unavailable, leave the verified
  migration intact, report the exact permission blocker, and do not pretend the
  old repository is gone.
- If local removal fails, report the remaining exact path; never broaden a
  recursive deletion target.

## Completion criteria

The work is complete only when `robium-apps` contains the consolidated catalog
and verified indoor-navigation implementation, all surviving repositories refer
only to `robium-apps`, the changes are pushed, the internal GitHub repository is
absent, its local checkout is removed from the original path, and the temporary
migration specification and plan no longer leave stale repository-name mentions
in the surviving tracked trees.
