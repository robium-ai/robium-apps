# Application registry (public index)

The quick index of promoted apps. Each app's `robium-app.yaml` is the
machine-readable contract (`robium-ai app list|describe|check|run` work from
a clone of this repo); the design standard is
[docs/reference-applications-design.md](docs/reference-applications-design.md).
Development history and battle-scar notes live in the private proving-ground
repo; this index carries only what a user of the public apps needs.

| App | Vertical | Stack | Sim | Env | Viz | Smoke |
| --- | --- | --- | --- | --- | --- | --- |
| [indoor-navigation](indoor-navigation/) | Classical ROS navigation | ROS 2 Jazzy + Nav2 + slam_toolbox | Gazebo Harmonic (headless) | Docker (arm64) | Lichtblick (bundled, browser) | `make smoke` |
| [imitation-manipulation](imitation-manipulation/) | Physical AI / ML manipulation | LeRobot 0.6.0 (ACT) | gym-pusht + PushShape variants | uv + Python 3.12 (MPS) + Docker (demo) | Gradio + Rerun (browser) | `make smoke` + `make demo-smoke` |
| [vla-language-learning](vla-language-learning/) | Language-conditioned VLA (experimental) | LeRobot 0.6.0 + SmolVLA 450M | MuJoCo 3.10 (SO-101) | uv + Python 3.12 (MPS) + HF Jobs (GPU train) | Rerun (+ gradio_rerun demo UI) | `make smoke` |
