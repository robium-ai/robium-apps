# Application registry

The canonical index of developed and published apps. Each app's `robium-app.yaml` is the
machine-readable contract (`robium-ai app list|describe|check|run` work from
a clone of this repo); the design standard is
[docs/reference-applications-design.md](docs/reference-applications-design.md).
Detailed battle scars live in each app's architecture brief and in the sibling
`robium` repository's dated learnings.

| App | Vertical | Stack | Sim | Env | Viz | Smoke |
| --- | --- | --- | --- | --- | --- | --- |
| [indoor-navigation](indoor-navigation/) | Classical ROS navigation | ROS 2 Jazzy + Nav2 + slam_toolbox | Gazebo Harmonic; Waffle Pi in selectable House and Warehouse environments from the shared pinned-asset catalog | Pixi/RoboStack (macOS arm64) + Docker | Native Gazebo + bundled Lichtblick + configurable Robium Dashboard `.foxe` | Runtime validation only; automated tests intentionally removed |
| [imitation-manipulation](imitation-manipulation/) | Physical AI / ML manipulation | LeRobot 0.6.0 (ACT) | gym-pusht + PushShape variants | uv + Python 3.12 (MPS) + Docker (demo) | Gradio + Rerun (browser) | `make smoke` + `make demo-smoke` |
| [vla-language-learning](vla-language-learning/) | Language-conditioned VLA (experimental) | LeRobot 0.6.0 + SmolVLA 450M | MuJoCo 3.10 (SO-101) | uv + Python 3.12 (MPS) + HF Jobs (GPU train) | Rerun (+ gradio_rerun demo UI) | `make smoke` |
| [robot-teleoperation](robot-teleoperation/) | Real-robot teleoperation | ROS 2 Humble + foxglove_bridge | TurtleBot 4 hardware | Robot host + browser client | Foxglove (browser) | `make smoke` (hardware-in-the-loop) |
| [quadruped-locomotion](quadruped-locomotion/) | Reinforcement-learning locomotion | Isaac Lab + rsl_rl PPO | Isaac Sim (Unitree Go2) | RunPod NVIDIA GPU | Browser control + recorded rollouts | `make smoke` (remote GPU) |
