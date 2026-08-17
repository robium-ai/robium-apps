# Lichtblick Robot Control Extension Design

**Date:** 2026-08-12

**Status:** approved in conversation

**Application:** robot-navigation

**Primary artifact:** reusable Lichtblick `.foxe` extension

## Summary

Build a standalone Lichtblick extension that contributes one `Robot Control` panel. The panel occupies a docked right rail in robot-navigation while the 3D/map view keeps most of the window. It combines teleoperation, map workflow controls, Home, Stop, connection state, and action feedback in one reusable surface.

The first version prioritizes a correct extension package and clean reuse boundary. It uses robot-navigation's existing ROS topics, parameters, and services. It does not dynamically replace the mapping ROS graph with the localization ROS graph; that orchestration remains a later backend improvement and the panel must not imply that it happened.

## Goals

- Provide mouse, touch, and keyboard WASD movement controls.
- Provide a map-name input, available-map selector, Start Mapping, Stop Mapping, and Load Map controls.
- Provide Go Home and Stop controls, with honest capability/status reporting.
- Use Lichtblick's supported extension API and `.foxe` packaging flow.
- Make ROS topic names, service names, parameters, speeds, and optional features configurable and persisted in the panel's layout state.
- Keep the 3D/map panel dominant on the left and the control panel docked on the right.
- Make the extension usable by future navigation applications without importing robot-navigation code.
- Preserve a stable extension and panel identity so saved layouts survive upgrades.

## Non-goals

- Forking or rebuilding Lichtblick.
- Automatically installing the extension into every browser profile or origin.
- Dynamically tearing down SLAM and launching AMCL/Nav2 localization from the panel.
- Implementing a production-grade emergency stop.
- Making Go Home functional when no backend service is configured.
- Reworking the existing map manager, teleop relay, or navigation stack beyond changes required to integrate and test the extension.

## Upstream basis

The design follows Lichtblick's official `create-lichtblick-extension` generator and its React and call-service examples:

- <https://github.com/Lichtblick-Suite/create-lichtblick-extension>
- <https://github.com/Lichtblick-Suite/create-lichtblick-extension/tree/main/examples/call-service-panel-example>

The installed web viewer supports local browser extensions through `IdbExtensionLoader("local")`. Dropped or opened `.foxe` files are unpacked and persisted in browser IndexedDB:

- <https://github.com/Lichtblick-Suite/lichtblick/blob/main/packages/suite-web/src/WebRoot.tsx>
- <https://github.com/Lichtblick-Suite/lichtblick/blob/main/packages/suite-base/src/hooks/useHandleFiles.tsx>
- <https://github.com/Lichtblick-Suite/lichtblick/blob/main/packages/suite-base/src/services/extension/IdbExtensionLoader.ts>

The panel uses the official `PanelExtensionContext` surface for subscriptions, publishing, service calls, parameter updates, persisted state, and cleanup:

- <https://github.com/Lichtblick-Suite/lichtblick/blob/main/packages/suite/src/index.ts>

These sources were inspected directly on 2026-08-12. The checked upstream commits were `e503b8eb63b099f9c7024d3aa6605db1240332df` for the generator and `64357108ce49764732f53183d89f363d57d50502` for Lichtblick.

## Repository placement

The reusable package lives outside the application-specific directory:

```text
shared/
└── lichtblick-robot-control/
    ├── package.json
    ├── package-lock.json
    ├── tsconfig.json
    ├── config.ts
    ├── README.md
    └── src/
        ├── index.ts
        ├── RobotControlPanel.tsx
        ├── panelConfig.ts
        ├── lichtblickAdapter.ts
        ├── messages.ts
        ├── styles.css
        └── *.test.tsx
```

Indoor-navigation owns only its integration:

```text
robot-navigation/
├── lichtblick/mapping-layout.json
├── Makefile
├── README.md
└── tests/
    └── test_lichtblick_control_layout.py
```

The shared package must not import from robot-navigation. Indoor-navigation supplies its defaults through the panel state embedded in `mapping-layout.json`.

## Stable extension identity

- Package `name`: `robot-control`
- Package `publisher`: `robium`
- Package `displayName`: `Robium Robot Control`
- Registered panel `name`: `robot-control`
- Panel type in a Lichtblick layout: `Robium Robot Control.robot-control`

These values are compatibility identifiers and must not be renamed casually. Lichtblick derives extension-panel types from the extension's qualified name and registered panel name; changing either breaks saved layouts.

## Component boundaries

### Extension entry point

`src/index.ts` exports `activate(extensionContext)` and registers exactly one panel. It contains no application logic.

### RobotControlPanel

The React component owns visible state and user interaction:

- connection/capability status;
- mapping/localization mode;
- map name and available map selection;
- pending operation and last result;
- WASD pointer, touch, and keyboard state;
- Home and Stop actions.

It receives an adapter and validated configuration rather than calling `PanelExtensionContext` throughout the component tree.

### Lichtblick adapter

The adapter is the only unit that touches `PanelExtensionContext`. It owns:

- topic subscriptions and `onRender` processing;
- the required `done()` render acknowledgement;
- advertising, publishing, and unadvertising the teleop topic;
- service calls;
- ROS parameter changes;
- saved panel state and settings-editor updates;
- cleanup on unmount.

This boundary makes the UI testable with a fake adapter and contains SDK compatibility changes to one module.

### Configuration

Panel state is a versioned, JSON-serializable object. Version 1 defaults are:

```json
{
  "version": 1,
  "teleopTopic": "/cmd_vel_teleop",
  "mappingStateTopic": "/mapping/state",
  "availableMapsTopic": "/maps/available",
  "mapNameParameter": "/map_manager.map_name",
  "startMappingService": "/mapping/reset",
  "stopMappingService": "/mapping/save",
  "loadMapService": "/mapping/load",
  "goHomeService": "",
  "navigationStopService": "",
  "linearSpeed": 0.2,
  "angularSpeed": 0.8,
  "publishRateHz": 10
}
```

Foxglove Bridge addresses ROS 2 parameters as `<fully-qualified-node-name>.<parameter-name>`; therefore robot-navigation's map parameter is `/map_manager.map_name`. Empty optional service names mean that the feature is unavailable, not that the panel should guess a service.

Configuration is editable through Lichtblick's panel settings and persisted with `context.saveState()`. Unknown future fields are ignored. Invalid or missing fields fall back individually to version 1 defaults.

## Layout and visual design

`mapping-layout.json` becomes a two-column top-level layout:

- left: 72%, a column containing the existing 3D/map view at 78% height and robot camera at 22% height;
- right: 28%, `Robium Robot Control.robot-control` for the full layout height.

Lichtblick still allows the user to resize either split. The committed defaults preserve a large primary map while giving the control panel enough width for its form controls.

The control panel uses a dark, restrained robot-console style inspired by the supplied Innate reference, without copying its navigation shell, camera overlay, joystick, arm controls, or typography. The panel is one continuous surface with four visually clear regions:

1. connection and current-mode header;
2. WASD drive controls;
3. mapping and map-selection controls;
4. Go Home and Stop actions.

The design follows the active Lichtblick light/dark color scheme, remains usable at narrow panel widths, uses visible text labels, and preserves browser focus indicators.

## Interaction behavior

### Teleoperation

- Pointer/touch press and keyboard `W`, `A`, `S`, and `D` produce commands while held.
- `W` and `S` set positive/negative `linear.x`; `A` and `D` set positive/negative `angular.z`.
- Conflicting opposites cancel on that axis; diagonal combinations may set linear and angular velocity together.
- The adapter advertises `/cmd_vel_teleop` with schema `geometry_msgs/msg/Twist` before publishing.
- While any movement input is held, the latest command is published at the configured rate, 10 Hz by default.
- Release, pointer cancellation, window blur, tab hiding, connection loss, config change, and component cleanup each publish one zero Twist when publishing is available.
- Keyboard commands are ignored while focus is in an input, select, textarea, button, or content-editable element.
- The existing `teleop_relay` deadman remains a second protection layer and converts Twist to the simulator's required TwistStamped command.

### Mapping and maps

The panel subscribes to `/mapping/state` (`std_msgs/msg/String`) and `/maps/available` (`std_msgs/msg/String`). Available maps are newline-separated names. Blank lines, the existing `<none saved yet>` sentinel, and duplicate names are removed.

Map names must be non-empty and match `^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$`. This prevents whitespace-only names, path traversal, and names that cannot be used safely as map basenames.

Before every map action, the panel calls `context.setParameter("/map_manager.map_name", selectedName)` and waits up to three seconds for the same value to appear in `renderState.parameters`. Only then does it call the map service. This acknowledgement step is required because `setParameter()` returns `void`; immediately calling the service would race the asynchronous bridge update and could act on the previous map name.

| Control | Enabled when | Version 1 action | Honest result |
| --- | --- | --- | --- |
| Start Mapping | connected, mode is `MAPPING`, valid name, no action pending | set map name, call `/mapping/reset` | fresh map started in the already-running mapping session |
| Stop Mapping | connected, mode is `MAPPING`, valid name, no action pending | set map name, call `/mapping/save` | map saved; SLAM backend remains alive |
| Load Map | connected, mode is `LOCALIZATION`, selected saved map, no action pending | set map name, call `/mapping/load` | selected map loaded into the already-running localization session |

The panel must never claim that Load Map changed a mapping session into localization. When the wrong mode is active, the disabled control explains which session is required.

### Home and Stop

- Go Home is always visible. It is disabled with `Not configured` when `goHomeService` is empty. When configured, it performs an empty-request service call and displays the response.
- Stop always publishes a zero Twist immediately when publishing is supported.
- If `navigationStopService` is configured, Stop also calls it after publishing zero.
- Without a navigation-stop backend, the control is labeled and documented as a motion command stop, not an emergency stop; Nav2 may publish a later command for an active goal.

## State flow

```text
foxglove_bridge
  ├─ /mapping/state ───────┐
  ├─ /maps/available ──────┼─> Lichtblick adapter ─> React panel state
  └─ connection methods ───┘

user input
  ├─ WASD ─> adapter.publish(/cmd_vel_teleop) ─> teleop_relay ─> /cmd_vel
  └─ map action
       ├─ adapter.setParameter(/map_manager.map_name)
       ├─ renderState.parameters confirms selected value
       └─ adapter.callService(configured endpoint)
```

The adapter watches only `topics`, `currentFrame`, `colorScheme`, and `parameters`. The configured state topics appearing in `renderState.topics` establish connection readiness. It subscribes only to the two configured state topics and always calls the render callback's `done()` exactly once. Optional `publish` and `callService` methods determine whether those controls can be offered. The current parameter map acknowledges map-name changes before a service call.

## Error handling and safety

- Missing optional `publish` or `callService` methods are visible in the panel and disable only the affected controls.
- If the requested map name is not confirmed in `renderState.parameters` within three seconds, the related map action aborts before its service call and displays a timeout error.
- Service actions are single-flight. Repeated clicks cannot start duplicate requests.
- A rejected service call preserves the current selection and shows a concise error.
- Service success displays the returned message when available.
- A map action never runs with an invalid name or the wrong session mode.
- Changing the teleop topic first publishes zero on the old topic, unadvertises it, then advertises the new topic.
- Cleanup clears timers and listeners, publishes zero when possible, unsubscribes, and unmounts React.
- No control is described as an emergency stop.

## Packaging and installation

The shared package uses the official Lichtblick extension toolchain and a committed npm lockfile. Scripts include:

- `npm test`
- `npm run lint`
- `npm run build`
- `npm run package`

Packaging produces a versioned `.foxe` artifact under the package's output directory. Generated build output and `.foxe` files are not committed. Indoor-navigation adds a convenience Make target that builds/packages the shared extension and prints the artifact path.

For the bundled web viewer, installation is one-time per browser origin:

1. build/package the extension;
2. open the robot-navigation Lichtblick viewer;
3. drag or open the `.foxe` file in Lichtblick;
4. reload if the current Lichtblick release requires it;
5. use the committed mapping layout containing the custom panel.

Browser IndexedDB persists the extension for that origin. A future deployment phase may embed or centrally provision the extension, but that is deliberately outside this design.

## Testing

### Unit tests

A fake adapter/`PanelExtensionContext` covers:

- pointer, touch, and keyboard press/release behavior;
- repeating commands while held and zero commands on every release/cleanup path;
- ignoring keyboard movement in form and editable controls;
- opposite-direction cancellation and diagonal movement;
- topic advertisement and cleanup;
- mode-based control availability;
- map-list parsing, selection, and validation;
- parameter update, render-state acknowledgement, and service-call ordering;
- single-flight service behavior;
- absent optional publish/service methods, parameter-confirmation timeouts, and rejected service calls;
- persisted settings and default migration.

Timers use fake time so teleop tests are deterministic.

### Packaging checks

- `npm ci`, lint, test, build, and package all pass.
- The `.foxe` archive contains a valid `package.json` and the compiled entry specified by `main`.
- Activating the bundle registers exactly `Robium Robot Control.robot-control`.

### Application integration tests

- `mapping-layout.json` parses as JSON.
- Its layout contains the stable extension panel type in the right branch.
- The main 3D panel remains the majority left branch.
- Indoor-navigation's existing Python tests pass.

### Live smoke test

Run the real mapping stack and bundled Lichtblick viewer, install the `.foxe`, and verify:

1. the panel renders and connects;
2. mapping state and available maps appear;
3. holding W produces teleop commands and robot motion;
4. releasing W produces zero and motion stops via the relay/deadman;
5. a non-destructive map action or disposable test map exercises parameter-plus-service ordering;
6. an unavailable Go Home action is clearly disabled;
7. the layout reloads with the custom panel intact.

The app change is not complete until this real-platform smoke test passes.

## Documentation and registry

- The shared extension README documents its configuration schema, build/package commands, installation, safety behavior, and reuse from another project.
- Indoor-navigation's README documents the one-time extension installation and revised mapping layout.
- `REGISTRY.md` is updated in the same implementation commit with the new panel and the date of the successful smoke pass.
- The app architecture brief records the extension boundary and the still-open mapping-to-localization orchestration limitation.

## Future work

The following are deliberately deferred:

- a persistent backend controller that transitions between mapping and localization graphs;
- a real Nav2 cancel/stop service;
- Go Home goal storage and execution;
- automatic extension provisioning for ephemeral/cloud viewer origins;
- optional gamepad/joystick input;
- multi-robot namespace selection.

Each deferred item changes backend or deployment architecture and should be designed independently rather than folded into the extension MVP.
