"""Single source of truth for vla-pick-and-place run parameters.

Every pin in this file is a pin on purpose. The app owns no physics, no
scene, and no task definition any more: the environment is the published
`so101-nexus` package and the demonstrations are published Hub datasets, so
"which version" IS the contract. A moving `main` here would silently change
the observation schema, the action units, or the success predicate under a
UI that claims to show them.

The Makefile targets and the tests both build their invocations from these
values, so a hand-run stage and the pass-bar run can never drift apart.
"""

import os
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]

# --- environment ------------------------------------------------------------
# The pinned upstream environment. `pyproject.toml` pins the same version as an
# install requirement; `tests/test_pins.py` asserts the two agree, so bumping
# one without the other fails the suite rather than the demo.
NEXUS_VERSION = "0.5.1"
ENV_ID = "MuJoCoPickAndPlace-v1"

# so101-nexus registers its MuJoCo ids from `so101_nexus.mujoco`; the Warp
# backend is a separate optional install this app deliberately does not use
# (it needs CUDA, and the local promise here is a native Mac/Linux run).
ENV_BACKEND = "mujoco"

# Camera observation size. 640x480 is what the published datasets recorded, so
# matching it keeps live frames and demonstration frames directly comparable.
# Measured on an M-series Mac: two camera observations cost ~60 env steps/s at
# ANY of 256x256/320x240/640x480 — the per-render fixed cost dominates, so the
# smaller sizes buy nothing and lose the dataset match.
CAMERA_W = 640
CAMERA_H = 480

# The keys `NexusPickAndPlace` normalizes upstream observations onto. They are
# LeRobot's names, not so101-nexus's (`wrist_camera`/`overhead_camera`/`state`),
# so a frame from the simulator and a frame from a demonstration dataset are
# the same dict shape everywhere above the adapter.
OBS_STATE = "observation.state"
OBS_ENV_STATE = "observation.environment_state"
OBS_WRIST = "observation.images.wrist"
OBS_OVERHEAD = "observation.images.overhead"
CAMERA_KEYS = (OBS_WRIST, OBS_OVERHEAD)

# SO-101: 5 arm joints + 1 gripper.
N_JOINTS = 6
JOINT_NAMES = (
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
    "gripper",
)

# The instruction both published datasets record for this task, verbatim. It
# is dataset metadata, NOT a prompt the app invents: nothing in this milestone
# is language-conditioned, so the UI shows it as provenance and does not offer
# it as an editable instruction box.
TASK = "Pick up the red cube and place it on the blue circle."

# Upstream's own episode cap for this env id (`gymnasium.registry`), restated
# here so the UI can show progress without importing gymnasium. Asserted
# against the live spec in tests/test_env.py.
MAX_EPISODE_STEPS = 1024

# One `step()` advances the simulator by `control_dt` seconds. Upstream is
# explicit that this is unrelated to a recording's wall-clock fps: a recorder
# sleeps to pace an operator but still advances the sim exactly one step per
# recorded frame. So one dataset frame == one env step, and the datasets' 30 /
# 33 fps figures are playback rates, not a control-rate mismatch.
CONTROL_DT = 0.02  # 50 Hz

# The recorder's fps. NOT a playback convention: `control_dt` is 0.02 s and one
# recorded frame is exactly one env step, so 50 is the real control rate. The
# published datasets use 30 / 33, which for them ARE playback rates.
CONTROL_FPS = 50

# Where `./app record` writes. A local dataset in the app's own scene, in the
# app's own units — see data/record.py for why it exists at all. Never pushed
# to the Hub by any code path here.
LOCAL_DATASET_REPO_ID = "robium/so101_nexus_pickplace_expert"

# Demo playback rate. The datasets were recorded for 30 fps playback and the
# simulator sustains ~60 steps/s with both cameras on, so 30 is honest for both
# sources and leaves headroom.
PLAYBACK_FPS = 30

# How many steps an "explore the simulator" run executes before stopping. Short
# enough that a visitor sees a beginning and an end; the env's own cap is
# MAX_EPISODE_STEPS.
EXPLORE_STEPS = 200

# --- datasets ---------------------------------------------------------------
# Both pins are commit shas, never `main`. `LeRobotDataset(..., revision=...)`
# takes them directly.
#
# PRIMARY. The upstream maintainer's own recording, and the only published
# MuJoCoPickAndPlace-v1 dataset whose frames were verified against this app's
# environment: see docs/architecture-brief.md for the side-by-side. It also
# ships `meta/so101_nexus_env.json` (the exact env config it was recorded
# with), reward/success channels, and env-native observation component names.
# Small (10 episodes) — a reference and a playback source, not training data.
DATASET_REPO_ID = "johnsutor/MuJoCoPickAndPlace-v1"
DATASET_REVISION = "8e295eba4e3c07e16af6a77b6b973e43b361adff"

# SECOND CANDIDATE, NOT INTERCHANGEABLE. 500 scripted-expert episodes with a
# published collector and a trained model — much better training material, and
# the reason it is registered at all. But its recorded frames are NOT this
# environment's: its scene has a wood-textured ground and an orange robot, and
# its `cam0` is an angled side view rather than so101-nexus's OverheadCamera,
# so its collector must have overridden the scene config. Its cameras are also
# named `cam0`/`cam1`, which carries no view identity. Using it means first
# reproducing its env config; do not point playback or a policy at it and
# assume the pixels match. See `data/datasets.py`.
DATASET_ALT_REPO_ID = "ataghof/so101nexus-cube500-binary"
DATASET_ALT_REVISION = "bdd2d23b85c54181f76d7f7f690ce4527d64b507"

# LeRobot dataset rows are NOT in simulator units. Body joints are recorded in
# DEGREES and the gripper as RANGE_0_100 percent of jaw travel, while the env's
# action space is radians. so101-nexus publishes the exact converters
# (`so101_nexus.lerobot_dataset.dataset_row_to_sim_qpos` and its inverse) and
# the adapter uses them — nothing in this app hand-rolls a deg2rad.
DATASET_UNITS = "lerobot"  # degrees + gripper percent
ENV_UNITS = "radians"

# --- rendering / viz --------------------------------------------------------
VIZ_DIR = APP_ROOT / "outputs" / "viz"
CONTRACT_JSON = APP_ROOT / "outputs" / "contract.json"

# JPEG quality for frames streamed into the embedded Rerun viewer. Raw RGB at
# 2 cameras x 640x480 x hundreds of steps is >100 MB down a browser stream.
STREAM_JPEG_QUALITY = 75

# --- demo -------------------------------------------------------------------
DEMO_PORT = int(os.environ.get("PORT", "8765"))
DEMO_SESSION_SECONDS = 1800
DEMO_FLEET_BUDGET = 1

# Seeds an "explore the simulator" run cycles through. Any seed works — the env
# resets deterministically for a fixed seed (verified in tests/test_env.py) —
# this just keeps consecutive clicks from showing the same cube placement.
DEMO_SIM_SEEDS = tuple(range(10))

# --- device -----------------------------------------------------------------
# Nothing in this milestone runs a policy, so this is only read when a
# controller from `policy/controllers.py` is actually selected. Kept out of
# import-time torch so the simulator and dataset paths never pay for it.
def inference_device() -> str:
    """Best available torch device, or the VLA_DEVICE override."""
    override = os.environ.get("VLA_DEVICE")
    if override:
        return override
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"
