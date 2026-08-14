# Robium Robot Control

A reusable Lichtblick extension panel for ROS 2 mobile robots. It combines manual WASD drive,
mapping lifecycle controls, map selection for localization, and optional home/stop services in a
compact right-side control rail.

## Build and install

```bash
npm ci
npm test
npm run lint
npm run package
```

The package command creates `robium.robot-control-0.3.0.foxe`. In Lichtblick Web, drag the `.foxe` onto
the viewer (or open it with the file picker), confirm installation, and add **Robium Robot Control →
robot-control** to a layout. Browser installation is stored in IndexedDB for that browser origin.

Desktop Lichtblick users can instead run `npm run local-install`.

The indoor-navigation app consumes this same package at image-build time and
preinstalls it before the bundled Lichtblick application starts. That app's
users therefore get the right-side panel by default; the manual flow above is
for reuse in other projects.

## Default ROS interfaces

| Purpose | Interface |
| --- | --- |
| Manual velocity | `/cmd_vel_teleop` (`geometry_msgs/msg/Twist`) |
| Mapping state | `/mapping/state` |
| Available maps | `/maps/available` |
| Simulation state | `/simulation/state` |
| Map-name parameter | `/session_manager.map_name` |
| Simulation-world parameter | `/session_manager.world` |
| Start mapping | `/mapping/start` |
| Stop/save mapping | `/mapping/stop` |
| Load for localization | `/mapping/load` |
| Restart simulation | `/simulation/restart` |

All interfaces can be changed in the panel settings sidebar. Go Home remains disabled until a
service is configured. The Stop Robot button always sends zero velocity and can optionally call a
configured navigation-stop service.

Map names are limited to 1–64 letters, numbers, dashes, or underscores. Map actions set the
map-name parameter, wait up to three seconds for the live ROS parameter state to acknowledge it,
then call the service.

## Safety

Manual commands publish at 10 Hz while held and publish zero on release, window blur, hidden tab,
configuration change, or panel removal. **Stop Robot is a motion-command stop, not a certified
emergency stop.** Keep a hardware emergency-stop path for real robots.

The panel requests lifecycle transitions through configured services. The robot
application owns the simulator, mapping, and localization process lifecycle.
