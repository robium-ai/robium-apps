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
| [imitation-manipulation](imitation-manipulation/) | ACT learns PushT from demos; probe generalization on unseen block shapes | LeRobot · ACT · gym-pusht · uv (MPS) · Gradio + Rerun | `make sync fetch-artifacts && make demo` |
| [vla-language-learning](vla-language-learning/) | Language-conditioned pick-and-place with SmolVLA on a simulated SO-101 arm (pipeline proven end-to-end; full-training policy pending) | LeRobot · SmolVLA · MuJoCo · uv (MPS) + HF Jobs | `make sync assets && make oracle` |
