# robium-apps

Polished, battle-tested robotics example applications built with the
[robium](https://github.com/robium-ai/robium) Claude Code plugin.

Each app here has passed its smoke test and a public-readiness review before
promotion. Apps arrive one at a time as they are validated — first up:
classical ROS 2 navigation (Nav2 + slam_toolbox + Gazebo Harmonic, fully
headless in Docker).

## Apps

| App | What it shows | Stack | Try it |
| --- | --- | --- | --- |
| [indoor-navigation](indoor-navigation/) | SLAM builds a map, Nav2 drives clicked goals, fully in sim, viewer bundled | ROS 2 Jazzy · Nav2 · slam_toolbox · Gazebo Harmonic · Docker | `make build && make demo` → http://localhost:8765 |
