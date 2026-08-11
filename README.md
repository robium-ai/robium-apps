# robium-apps

Battle-tested robotics applications built with the
[robium](https://github.com/robium-ai/robium) plugin.

This is the canonical development and distribution repository. Each app keeps
its environment, tests, architecture brief, and machine-readable contract in
one directory; app sessions also capture skill learnings in the sibling
`robium` repository.

- **Standard:** [docs/reference-applications-design.md](docs/reference-applications-design.md)
- **Adding an app:** [CONTRIBUTING.md](CONTRIBUTING.md)
- **CLI:** `npx robium-ai app list` from a clone of this repo (or
  `app check <id>` / `app run <id>`)

## Apps

| App | What it shows | Stack | Try it |
| --- | --- | --- | --- |
| [indoor-navigation](indoor-navigation/) | SLAM builds a map, Nav2 drives clicked goals, fully in sim, viewer bundled | ROS 2 Jazzy · Nav2 · slam_toolbox · Gazebo Harmonic · Docker | `make build && make demo` → http://localhost:8765 |
| [imitation-manipulation](imitation-manipulation/) | ACT learns PushT from demos; probe generalization on unseen block shapes | LeRobot · ACT · gym-pusht · uv (MPS) · Gradio + Rerun | `make sync fetch-artifacts && make demo` |
| [vla-language-learning](vla-language-learning/) | Language-conditioned pick-and-place with SmolVLA on a simulated SO-101 arm (pipeline proven end-to-end; full-training policy pending) | LeRobot · SmolVLA · MuJoCo · uv (MPS) + HF Jobs | `make sync assets && make oracle` |
| [robot-teleoperation](robot-teleoperation/) | Browser teleoperation, LiDAR status, and dock/undock controls for a real TurtleBot 4 | ROS 2 Humble · foxglove_bridge · TurtleBot 4 | `make check`; `make smoke` with the robot |
| [quadruped-locomotion](quadruped-locomotion/) | Train and pilot a Unitree Go2 locomotion policy on a cloud NVIDIA GPU | Isaac Lab · Isaac Sim · rsl_rl PPO · RunPod | `make check`; `make smoke` on a GPU pod |
