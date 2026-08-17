# Named Waypoints Design

**Date:** 2026-08-14

**Scope:** robot-navigation waypoint capture and navigation

## Goal

Let an operator name the robot's current localized pose, see the waypoints saved for the active map, navigate to one, and delete one from the existing Robot Control panel.

## User experience

Robot Control gains a compact **Waypoints** card containing:

- one validated waypoint-name field;
- **Save current position**;
- an alphabetical list of waypoints for the active map; and
- **Navigate** and **Delete** actions on each row.

Saving captures the live `map -> base_footprint` transform. It never captures a clicked 3D-map pose. Save, navigate, and delete are available only in `LOCALIZATION`, where an active saved map and stable map-frame pose exist. Duplicate names are rejected instead of overwriting an existing waypoint.

The existing status banner reports service success and exact backend errors. A successful navigate request means the stored goal was published to Nav2; it does not claim that the robot reached the waypoint.

## Ownership and data flow

Waypoint persistence and TF lookup live on the robot side. Browser-local persistence was rejected because it would bind robot data to one browser profile and require the extension to reconstruct ROS TF.

The existing session manager already owns the active world, map, and navigation process, so it exposes the waypoint boundary:

- parameter `/session_manager.waypoint_name`;
- latched topic `/waypoints/available` as newline-separated names;
- Trigger services `/waypoints/save`, `/waypoints/navigate`, and `/waypoints/delete`.

Robot Control adds configurable names for those interfaces. Before a waypoint service call, the adapter sets `waypoint_name` and waits for the parameter acknowledgement, matching the existing race-safe map-action pattern.

`Save` looks up the latest `map -> base_footprint` transform and stores position plus yaw. `Navigate` loads the named pose and publishes a `geometry_msgs/msg/PoseStamped` goal to `/goal_pose`. `Delete` removes only the named waypoint. Every mutation republishes the active waypoint-name list.

## Storage

Waypoints are scoped by world and map. For a map at:

```text
<maps-root>/<world>/<map>.yaml
```

the waypoint sidecar is:

```text
<maps-root>/<world>/<map>.waypoints.json
```

The JSON document contains a version and a name-keyed object of finite `x`, `y`, and `yaw` values. Writes use a temporary sibling followed by an atomic replace so interruption cannot leave a partially written file. Names use the existing 1–64 character letters/numbers/dashes/underscores rule.

The sidecar is local runtime data, like user-saved maps. It is never created until the operator saves a waypoint and is not committed. Implementation and automated tests must not modify, delete, or stage the worktree's existing untracked saved-map directories.

## Components

### Waypoint store

A ROS-independent Python class owns validation, JSON parsing, sorting, atomic writes, duplicate rejection, lookup, and deletion. Tests use temporary directories.

### Session manager

The ROS node owns a TF buffer/listener, a `/goal_pose` publisher, waypoint services, and the latched waypoint list. It delegates file operations to the waypoint store and refuses actions outside localization or without an active map.

### Robot Control extension

The panel configuration schema gains waypoint topic, parameter, and service fields with defaults. Older saved panel states normalize missing fields to those defaults. The adapter subscribes to the list topic and exposes one waypoint action method. The React panel renders and gates the compact controls.

## Failure behavior

- No active localization map: refuse the action with an explicit mode error.
- Invalid or duplicate name: refuse without changing storage.
- Missing TF: refuse Save and preserve storage.
- Missing waypoint: refuse Navigate/Delete.
- Malformed sidecar: report the parse/validation error and do not overwrite it.
- Goal publication failure at the service boundary: return a failed Trigger response.
- Parameter acknowledgement timeout or unavailable service: reuse the panel's status-banner error path.

## Verification

Focused tests cover:

- waypoint-store round trips, alphabetical listing, duplicate rejection, deletion, malformed data, and per-map isolation;
- session-state gating and active-map selection without touching real map files;
- extension parsing, acknowledged service calls, localization gating, and user interactions; and
- layout defaults matching the extension configuration.

Completion also requires the existing Python and extension suites plus the real navigation smoke test. The smoke must run with no competing simulator stack and must not mutate the untracked saved maps.

## Out of scope

- Saving a pose clicked in the 3D panel.
- Editing or renaming a waypoint.
- Waypoint sequences or patrol routes.
- Claiming navigation completion in the panel.
- The Lichtblick long-press publish-tool design.
- Final release-wide map and asset storage policy.
