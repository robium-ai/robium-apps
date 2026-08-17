# Mapping Toggle Design

## Goal

Replace separate Start mapping and Stop mapping controls with one compact state-aware button beside the map-name input.

## Design

The Maps card displays the map-name input on the left and one action button on the right. In every non-mapping state the button reads `Start mapping` and calls `/mapping/start`. While the live mapping state is `MAPPING`, it reads `Finish mapping` and calls `/mapping/stop`, which saves the selected map and returns the session to IDLE.

The map-name input is disabled while mapping so the save target cannot change during the session. Start requires a valid name; Finish depends only on service availability and the panel not being busy.

## Constraints

- Preserve the existing map-name validation and backend services.
- Do not add or run automated tests, lint, build, or smoke checks.
- Leave saved maps and waypoint sidecars untouched and untracked.
