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
| [diffusion-policy-pusht](diffusion-policy-pusht/) | Physical AI / ML manipulation (experimental) | LeRobot 0.6.0 + pinned official 175k Diffusion Policy | untouched gym-pusht T benchmark + custom L-I-Z OOD probes | uv + Python 3.12 + native Apple MPS or baked CPU demo image; no training required | Direct Gradio frames + additive Rerun timeline; website lifecycle gateway | `./app doctor` + launcher lifecycle + `make smoke` (2) + `make demo-smoke` (3) + CPU container/site lifecycle, all passed 2026-08-22; CPU seed 1000 solved in 116 steps at 0.953 raw coverage; published reference: 65.4% / 500 episodes |
| [act-aloha-cube-transfer](act-aloha-cube-transfer/) | Physical AI / bimanual imitation learning (experimental) | LeRobot 0.6.1 + pinned official ACT 80k checkpoint | gym-aloha ALOHA Transfer Cube on MuJoCo | uv + Python 3.12 + native Apple MPS or baked CPU demo image; no training required | Direct Gradio top camera + additive Rerun joint/action/reward timeline; website lifecycle gateway | `./app doctor` + `make smoke` + actual browser + CPU container/session/API lifecycle passed 2026-08-23; MPS seed 1001 transferred in 236 steps; bounded local calibration 2/5; published reference: 83% / 500 episodes |
| [vla-pick-and-place](vla-pick-and-place/) | Language-conditioned VLA (experimental) | pinned LeRobot v0.4.4 + official Pi0.5 LIBERO checkpoint | LIBERO-Goal task 8 (Franka Panda) | uv + Python 3.10; fake local fixtures; pinned Linux/amd64 CUDA image for RunPod | capability-scoped Gradio simulator frames | Doctor, 20 tests, fake rollout, and protected CPU lifecycle passed 2026-08-24; corrected RTX PRO 4500 retry passed CUDA and exact checkpoint bootstrap but produced no measured episode before confirmed deletion, so later gates remain blocked |
| [robot-teleoperation](robot-teleoperation/) | Real-robot teleoperation | ROS 2 Humble + foxglove_bridge | TurtleBot 4 hardware | Robot host + browser client | Foxglove (browser) | `make smoke` (hardware-in-the-loop) |
| [quadruped-locomotion](quadruped-locomotion/) | Reinforcement-learning locomotion | Isaac Lab + rsl_rl PPO | Isaac Sim (Unitree Go2) | RunPod NVIDIA GPU | Browser control + recorded rollouts | `make smoke` (remote GPU) |
