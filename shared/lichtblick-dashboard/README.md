# Robium Dashboard

A configurable Lichtblick extension for operating ROS 2 mobile robots. One
Dashboard package can provide movement, mapping, navigation and waypoints,
simulation controls, and safety actions without making every application fork
the panel source.

## Use it in an app

1. Install a pinned Dashboard `.foxe` in Lichtblick.
2. Add **Robium Dashboard → dashboard** to the app's layout.
3. In panel settings, enable the sections the app supports and enter its ROS
   topics, parameters, and services.
4. Export and commit the configured Lichtblick layout with the app.
5. Bundle the pinned `.foxe` with the app when users should receive a turnkey
   dashboard.

The generic default enables **Movement** and **Quick actions** only, publishing
`geometry_msgs/msg/Twist` on `/cmd_vel`. Maps, navigation, waypoints, and
simulation are opt-in capabilities. Indoor-navigation is a complete example:
its committed layout enables every section, uses an app-side adapter for its
lifecycle services, and supplies its House and Warehouse choices.

## Build and install

```bash
npm ci
npm run package
```

The package command creates `robium.dashboard-0.9.0.foxe`. In Lichtblick Web,
drag the `.foxe` onto the viewer (or open it with the file picker), confirm the
installation, and add **Robium Dashboard → dashboard** to a layout. Browser
installation is stored for that browser origin. Desktop Lichtblick developers
can instead run `npm run local-install`.

The `.foxe` is compiled output and is not intended to be edited. For deeper
customization, edit this extension's TypeScript source and build another
package, contribute reusable improvements upstream, or add a companion
Lichtblick panel beside Dashboard.

## Configuration

The settings sidebar exposes these section switches:

- Movement
- Maps and mapping
- Navigation and waypoints
- Simulation
- Quick actions

ROS interface names are editable in the same sidebar. Values that belong to an
application rather than the reusable panel—such as the available simulation
worlds—are stored in the app's layout JSON. A configured world list has this
shape:

```json
"simulationWorlds": [
  { "value": "furnished_house", "label": "House" },
  { "value": "tugbot_warehouse", "label": "Warehouse" }
]
```

The optional richer sections use configurable defaults such as
`/mapping/state`, `/maps/available`, `/navigation/state`, and
`/navigation/stop`. Applications can expose those interfaces directly or keep
their native ROS API and provide a small adapter node. Dashboard does not
require every robot application to adopt a new ROS protocol.

Map and waypoint names are limited to 1–64 letters, numbers, dashes, or
underscores. Save position records the current map-frame pose through the
configured app service. Stop Robot publishes zero velocity and, when Navigation
is enabled, also calls the configured navigation-stop service.

## Safety

Manual commands publish at the configured rate while held and publish zero on
release, window blur, hidden tab, configuration change, or panel removal.
**Stop Robot is a motion-command stop, not a certified emergency stop.** Keep a
hardware emergency-stop path for real robots.

## Distribution

During development, apps can build and preinstall Dashboard from this shared
folder. Versioned `.foxe` files can later be attached to Robium GitHub Releases
so external apps can pin a package without cloning this repository. Publishing
that release is intentionally separate from building the extension.
