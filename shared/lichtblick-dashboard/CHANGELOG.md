# Changelog

## 0.9.0 - 2026-08-14

- Adopt the Robium Dashboard name for the reusable extension.
- Default to a portable movement-and-stop dashboard for generic ROS 2 apps.
- Let layouts enable maps, navigation and waypoints, simulation, and quick actions independently.
- Move simulation world choices into app-owned layout configuration.
- Keep version-3 saved panel state working as a full legacy dashboard.

## 0.8.0 - 2026-08-14

- Combine map-name entry and mapping lifecycle into one compact row.
- Switch the action between Start mapping and Finish mapping from live state.
- Lock the map name during an active mapping session.

## 0.7.1 - 2026-08-14

- Migrate the legacy empty navigation-stop setting to `/navigation/stop` when loading version-2 panel state.

## 0.7.0 - 2026-08-14

- Merge waypoint controls into a Navigation card with live goal status.
- Add a Stop navigation action backed by a configurable ROS service.
- Default Stop Robot to cancel active navigation as well as publish zero velocity.

## 0.6.0 - 2026-08-14

- Remove the unused Go Home quick action and configuration.
- Leave Stop Robot as the single full-width quick action.

## 0.5.0 - 2026-08-14

- Add named current-position waypoint save, list, navigate, and delete controls.
- Scope waypoint actions to the active localization map through configurable ROS interfaces.

## 0.4.0 - 2026-08-14

- Simplify the simulation selector to House and Warehouse.
- Default the selector to the furnished House environment.

## 0.3.0 - 2026-08-14

- Replace the unreliable single-room simulation choice with Furnished House.

## 0.2.0 - 2026-08-14

- Add a four-world simulation selector and restart action.
- Support IDLE-first mapping, stop-and-save, and localization transitions.
- Add persisted forward/turn speed sliders and compact narrow-rail styling.
- Surface ROS Trigger refusals and synchronize the selected world from live state.

## 0.1.0 - 2026-08-12

- Add reusable WASD/arrow-key velocity controls with release and focus-loss stopping.
- Add mapping start/save, available-map loading, mode gating, and parameter acknowledgement.
- Add optional home and navigation-stop services plus editable panel settings.
