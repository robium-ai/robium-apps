# Navigation Plan and Quick Actions Design

## Goal

Make Nav2's global and local paths visually distinct in the bundled Lichtblick 3D map, and simplify Quick Actions to only Stop Robot.

## Design

- Keep `/plan` visible as a thick cyan global route.
- Add `/local_plan` as a visible orange local-controller path.
- Remove Go Home from Quick Actions and let Stop Robot fill the row.
- Remove `goHomeService` from Robot Control's configuration, settings, bundled layout, and documentation.
- Bump the Robot Control extension to `0.6.0` so the bundled viewer installs the changed panel instead of retaining the `0.5.0` artifact.

## Constraints

- Keep Stop Robot's current zero-velocity behavior and optional `navigationStopService` call.
- Do not change Nav2 publishers; consume the existing `nav_msgs/msg/Path` topics.
- Do not add or run automated tests, lint, build, or smoke checks.
- Do not modify, stage, or commit locally saved maps or waypoint sidecars.
