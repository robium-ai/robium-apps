# Tabbed Node Logs Design

## Goal

Replace the dashboard's single Logs panel with three compact tabs that make the
same ROS 2 `/rosout` stream useful at different levels of detail.

## Design

The lower-left dashboard region remains the same size and becomes a Lichtblick
`Tab` panel. It contains three child `RosOut` panels:

- **All** shows all INFO-and-higher messages from `/rosout`.
- **Navigation** filters by the app's Nav2 and localization node names:
  `amcl`, `map_server`, `controller_server`, `smoother_server`,
  `planner_server`, `behavior_server`, `bt_navigator`, `waypoint_follower`,
  `velocity_smoother`, `collision_monitor`, and
  `lifecycle_manager_navigation`.
- **Mapping & App** filters by `slam_toolbox`, `session_manager`, and
  `teleop_relay`.

Lichtblick's log search terms match either node names or message text and use
OR semantics. That provides a stable allow-list-like view without encoding an
exhaustive blacklist of every node that might appear at runtime. Operators can
still edit the visible filter tags in each tab.

## Layout and State

**All** is active by default. Camera, 3D, Robot Control, and all existing split
percentages remain unchanged. Only `mapping-layout.json` changes at runtime;
the extension package version does not change and no image rebuild is needed.

As with every committed default-layout update, an existing Lichtblick browser
origin may retain its previously saved layout. Clearing that origin's site data
or opening a fresh origin loads the new default.

## Verification Constraint

Do not add or run automated tests. Review the committed layout diff only, per
the project's explicit prototype-development preference.

