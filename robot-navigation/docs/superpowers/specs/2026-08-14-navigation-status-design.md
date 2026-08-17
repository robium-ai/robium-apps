# Navigation Status and Stop Design

## Goal

Merge waypoint controls into a Navigation card that reports whether Nav2 has an active goal and can cancel that goal.

## Robot-side interface

`session_manager` observes Nav2's `/navigate_to_pose/_action/status`. Goals in accepted, executing, or canceling states count as active. It republishes a latched `/navigation/state` string as `NAVIGATING` or `IDLE`, so the viewer does not need to understand ROS action internals.

A new Trigger service at `/navigation/stop` sends the zero-ID, zero-timestamp `action_msgs/srv/CancelGoal` request to `/navigate_to_pose/_action/cancel_goal`, which is Nav2's cancel-all policy. It reports an already-idle state without treating it as an error.

This observes and cancels goals regardless of whether they came from a saved waypoint or the 3D map.

## Control panel

The existing Waypoints card becomes Navigation. Its header includes a `Navigating` or `Not navigating` indicator and a full-width Stop navigation button, followed by the waypoint name input and saved-waypoint list. Stop navigation is enabled only while a goal is active.

Quick Actions keeps Stop Robot. Stop Robot publishes zero manual velocity and also calls `/navigation/stop`; Stop navigation only cancels the Nav2 goal.

Robot Control adds configurable `navigationStateTopic` and keeps `navigationStopService`, with defaults `/navigation/state` and `/navigation/stop`.

When loading a saved version-2 panel configuration, an empty legacy `navigationStopService` migrates to the version-3 default. An explicitly empty value saved by version 3 remains empty, so operators can still disable the service.

## 3D visibility cleanup

- Show `/map`, `/robot_description`, `/scan`, `/plan`, and `/local_plan`.
- Reduce scan point size from 4 to 2.
- Render `/plan` cyan and `/local_plan` orange.
- Explicitly hide `/received_global_plan`, `/transformed_global_plan`, `/plan_smoothed`, both costmaps, and transform labels.

## Constraints

- Do not add or run automated tests, lint, build, or smoke checks.
- Leave saved maps and waypoint sidecars untouched and untracked.
- Do not infer navigation from velocity; action status is authoritative.
