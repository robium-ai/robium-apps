# Application registry

The canonical index of developed and published apps. Each app's `robium-app.yaml` is the
machine-readable contract (`robium-ai app list|describe|check|run` work from
a clone of this repo); the design standard is
[docs/reference-applications-design.md](docs/reference-applications-design.md).
Detailed battle scars live in each app's architecture brief and in the sibling
`robium` repository's dated learnings.

| App | Vertical | Stack | Sim | Env | Viz | Smoke |
| --- | --- | --- | --- | --- | --- | --- |
| [robot-navigation](robot-navigation/) | Classical ROS navigation | ROS 2 Jazzy + Nav2 + slam_toolbox | Gazebo Harmonic; Waffle Pi in selectable House and Warehouse environments from the shared pinned-asset catalog | Pixi/RoboStack (macOS arm64) + Docker + per-visitor Cloud Run | Native Gazebo + bundled Lichtblick + configurable Robium Dashboard `.foxe` | `./app doctor` + local and Cloud Run runtime validation (2026-08-16) |
| [imitation-manipulation](imitation-manipulation/) | Physical AI / ML manipulation | LeRobot 0.6.0 (ACT) | gym-pusht + PushShape variants | uv + Python 3.12 (MPS) + Docker (demo) | Gradio + Rerun (browser) | `make smoke` + `make demo-smoke` |
| [vla-pick-and-place](vla-pick-and-place/) | Manual manipulation + published demonstrations (experimental; no trained controller yet) | so101-nexus 0.5.1 + LeRobot 0.6.0; scripted expert records training data in-scene (79/100 seeds) | MuJoCo 3.10 (SO-101), upstream `MuJoCoPickAndPlace-v1` | uv + Python 3.12, CPU-only (no GPU) | Robium workspace, in-page camera + joint readout; Rerun `.rrd` offline | `./app doctor` + `make test` (10, ~2.5 s) + `make dataset-check` + `make demo-smoke` (3) from a clean checkout (2026-08-17) |
| [robot-teleoperation](robot-teleoperation/) | Real-robot teleoperation | ROS 2 Humble + foxglove_bridge | TurtleBot 4 hardware | Robot host + browser client | Foxglove (browser) | `make smoke` (hardware-in-the-loop) |
| [quadruped-locomotion](quadruped-locomotion/) | Reinforcement-learning locomotion | Isaac Lab + rsl_rl PPO | Isaac Sim (Unitree Go2) | RunPod NVIDIA GPU | Browser control + recorded rollouts | `make smoke` (remote GPU) |
