"""Which controllers may drive this environment, and on what evidence.

The previous version of this app shipped a "trained controller" that scored
0/10 because it had been fine-tuned for a scene that no longer existed. It
failed silently-ish: the UI ran it, the arm flailed, and the only signal was a
sentence in a note. The fix is not a better checkpoint — it is making
compatibility a *declared, checked* property, so a controller that cannot
match this environment is unavailable rather than disappointing.

Each `Controller` records the fields that must line up for a rollout to mean
anything: repo and pinned revision, policy family and LeRobot version,
observation and action schema, camera names and resolution, control rate and
action horizon, device and memory, the environment id it was trained against,
and both published and locally reproduced evaluation results.

Two rules this module exists to enforce:

  * **Nothing falls back.** A selected controller that fails its check raises
    with the mismatched field named. It never degrades into dataset playback
    or a scripted motion, because a viewer cannot tell those apart from a
    policy rollout by looking.
  * **Unproven is unavailable.** `available` is False until a controller has
    been checked against this environment on this machine. "Published
    evaluation exists" is not that check.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from vla_pick_and_place.config import (
    CAMERA_H,
    CAMERA_W,
    CONTROL_DT,
    ENV_ID,
    N_JOINTS,
    NEXUS_VERSION,
    OBS_OVERHEAD,
    OBS_STATE,
    OBS_WRIST,
)
from vla_pick_and_place.env.contract import EXPECTED

ACTION_UNITS = EXPECTED["action_units"]


class IncompatibleController(RuntimeError):
    """A controller cannot be run here, with the mismatched field named."""


@dataclass(frozen=True)
class Controller:
    key: str
    label: str
    available: bool
    """Runnable on this machine, against this environment, verified locally."""
    unavailable_reason: str
    """Why not, in plain words. Shown verbatim in the UI. Empty when available."""

    repo_id: str = ""
    revision: str = ""
    family: str = ""
    lerobot_version: str = ""
    observation_keys: tuple[str, ...] = ()
    observation_shapes: dict[str, tuple[int, ...]] = field(default_factory=dict)
    action_shape: tuple[int, ...] = (N_JOINTS,)
    # Compared verbatim against the measured contract's `action_units`, so the
    # default is that exact string — a controller that emits anything else
    # (dataset rows, end-effector deltas) states its own and fails the check.
    action_units: str = ACTION_UNITS
    camera_keys: tuple[str, ...] = (OBS_WRIST, OBS_OVERHEAD)
    camera_resolution: tuple[int, int] = (CAMERA_H, CAMERA_W)
    control_dt: float = CONTROL_DT
    action_horizon: int | None = None
    required_device: str = ""
    estimated_memory_gb: float | None = None
    env_id: str = ENV_ID
    env_version: str = NEXUS_VERSION
    published_eval: str = ""
    local_eval: str = ""

    def require_available(self) -> None:
        if not self.available:
            raise IncompatibleController(f"{self.label}: {self.unavailable_reason}")


# The published MolmoAct2 LoRA. Registered because it is the one trained
# artifact with a full published chain (dataset + collector + eval harness),
# and deliberately NOT available: it was trained on the alternate dataset,
# whose recorded scene is not this environment's (see data/datasets.py), and
# it is a ~6B model evaluated on a 24 GB GPU. Either fact alone would block
# it; the app states both rather than advertising a controller nobody local
# can run.
MOLMOACT2 = Controller(
    key="molmoact2",
    label="MolmoAct2 LoRA (published, CUDA only)",
    available=False,
    unavailable_reason=(
        "Not runnable here, for two independent reasons. It was trained on "
        "ataghof/so101nexus-cube500-binary, whose recorded scene is not this "
        "environment's (different ground, robot colour, and camera placement), "
        "so its observations would not match these frames. And it is a ~6B "
        "model that its authors evaluated on a 24 GB CUDA GPU; no measurement "
        "of it on Apple Silicon exists in this repository. Reproducing its "
        "scene config and measuring it on a matching GPU are both prerequisites."
    ),
    repo_id="ataghof/molmoact2-so101nexus-lora-champion",
    family="molmoact2 (LoRA)",
    observation_keys=(OBS_STATE, OBS_WRIST, OBS_OVERHEAD),
    observation_shapes={OBS_STATE: (N_JOINTS,)},
    action_units="lerobot rows (degrees + gripper percent), binary gripper",
    camera_keys=("observation.images.cam0", "observation.images.cam1"),
    camera_resolution=(CAMERA_H, CAMERA_W),
    required_device="cuda",
    estimated_memory_gb=24.0,
    env_id=ENV_ID,
    published_eval=(
        "Authors report 93% grasp, 50% loose placement, 30% strict placement "
        "over 30 held-out cube positions, in their own scene configuration."
    ),
    local_eval="none — never run in this repository",
)

# The intended local controller. Deliberately a placeholder with no repo id:
# there is no ACT checkpoint trained against this pinned environment yet, and
# inventing a stand-in is what produced the 0/10 shipped controller. The
# follow-up training block fills this in.
LOCAL_ACT = Controller(
    key="act",
    label="Local ACT baseline (not trained yet)",
    available=False,
    unavailable_reason=(
        "No ACT checkpoint has been trained against this pinned environment "
        "yet. There is no lightweight ACT or SmolVLA checkpoint published for "
        f"{ENV_ID} at so101-nexus {NEXUS_VERSION} that runs comfortably on "
        "Apple Silicon, and this app will not substitute one trained "
        "elsewhere. See docs/training-guide.md."
    ),
    family="act",
    observation_keys=(OBS_STATE, OBS_WRIST, OBS_OVERHEAD),
    observation_shapes={
        OBS_STATE: (N_JOINTS,),
        OBS_WRIST: (CAMERA_H, CAMERA_W, 3),
        OBS_OVERHEAD: (CAMERA_H, CAMERA_W, 3),
    },
    required_device="cpu/mps",
    env_id=ENV_ID,
    published_eval="none",
    local_eval="none — not trained yet",
)

# The closest published policy to this environment, and still not close enough.
# Registered because it is the best evidence available that this task is
# learnable on consumer hardware — 380 episodes, a real evaluation battery, and
# an ablation showing the policy follows the words rather than the colours —
# and because a future maintainer WILL find it and needs the reasons written
# down rather than rediscovering them.
#
# Its scene is a two-disc subclass: a green and a blue disc are visible at all
# times and the instruction alone says which is the goal. That is the entire
# point of the model, and this environment has ONE disc, so the observation it
# was trained to disambiguate does not exist here. Measured: its overhead frame
# sits 0.091 from a live render — much closer than MolmoAct2's scene, and still
# well outside the 0.05 scene tolerance, because of the extra disc and a
# different overhead camera pose.
#
# The version gap is the harder blocker. Its code imports `so101_nexus_core` /
# `so101_nexus_mujoco`, the split packages of so101-nexus 0.3.x — those module
# names do not exist in 0.5.1. It also builds its own worldbody XML around
# `so101_new_calib.xml`, and applies runtime contact hardening its own authors
# describe as "a different world" that must be matched at evaluation. Adopting
# it means downgrading so101-nexus 0.5.1 -> 0.3.12 and LeRobot 0.6.0 -> 0.4.4
# and vendoring their scene: forking their project, not loading a checkpoint.
TWO_DISC_SMOLVLA = Controller(
    key="two-disc-smolvla",
    label="Two-disc SmolVLA (published, different scene)",
    available=False,
    unavailable_reason=(
        "Trained on a two-disc variant of this scene, where a green and a blue "
        "target are both always visible and the instruction says which one to "
        "use. This environment has a single disc, so the distinction the "
        "policy exists to make is not present in these frames (its overhead "
        "view measures 0.091 from a live render against a 0.05 tolerance). It "
        "also targets so101-nexus 0.3.12 and LeRobot 0.4.4 — its code imports "
        "the `so101_nexus_core` / `so101_nexus_mujoco` split packages that 0.5.1 "
        "no longer has — and requires the authors' contact-hardening physics at "
        "evaluation. Running it means adopting their fork, not loading a "
        "checkpoint."
    ),
    repo_id="zwan1003/pickplace_skills_vla_v3_2_ckpt060k",
    family="smolvla",
    lerobot_version="0.4.4",
    observation_keys=(OBS_STATE, OBS_WRIST, OBS_OVERHEAD),
    observation_shapes={OBS_STATE: (N_JOINTS,)},
    # Notably the one thing it gets right that the datasets do not: it was
    # recorded in the simulator's own radians, not LeRobot degrees.
    action_units=ACTION_UNITS,
    camera_keys=("observation.images.overhead_camera", "observation.images.wrist_camera"),
    camera_resolution=(224, 224),
    required_device="cpu/mps/cuda (450M)",
    estimated_memory_gb=2.0,
    env_id="TwoDiscPickPlaceEnv (subclass of MuJoCoPickAndPlace-v1)",
    env_version="0.3.12",
    published_eval=(
        "Authors report 33% grasp, 97% placement once held, 37% whole task over "
        "120-150 episodes on unseen start positions, in their two-disc scene. "
        "Ablation: 87% with both discs recoloured grey, 3% with the direction "
        "word removed — it follows language, not colour."
    ),
    local_eval="none — its scene cannot be constructed on the pinned environment",
)

REGISTRY: dict[str, Controller] = {
    c.key: c for c in (LOCAL_ACT, MOLMOACT2, TWO_DISC_SMOLVLA)
}


def get(key: str) -> Controller:
    try:
        return REGISTRY[key]
    except KeyError:
        raise IncompatibleController(
            f"unknown controller {key!r}; registered: {sorted(REGISTRY)}"
        ) from None


def available() -> list[Controller]:
    """Controllers that can actually run here. Currently empty, and honest."""
    return [c for c in REGISTRY.values() if c.available]


def check_against_env(controller: Controller, measured: dict[str, Any]) -> list[str]:
    """Compare a controller's declared schema to a measured env contract.

    Returns field-level mismatch messages; empty means compatible. Used by
    `run contract` to show *why* a controller is blocked in schema terms, and
    by any future controller as its admission test.
    """
    problems: list[str] = []
    if controller.env_id != measured.get("env_id"):
        problems.append(
            f"env_id: controller expects {controller.env_id!r}, "
            f"environment is {measured.get('env_id')!r}"
        )
    if list(controller.action_shape) != list(measured.get("action_shape", [])):
        problems.append(
            f"action_shape: controller expects {list(controller.action_shape)}, "
            f"environment provides {measured.get('action_shape')}"
        )
    env_cams = {OBS_WRIST, OBS_OVERHEAD}
    unknown = [c for c in controller.camera_keys if c not in env_cams]
    if unknown:
        problems.append(
            f"camera_keys: controller reads {unknown}, which this environment "
            f"does not produce (it produces {sorted(env_cams)})"
        )
    want_res = list(controller.camera_resolution) + [3]
    if want_res != list(measured.get("camera_shape", [])):
        problems.append(
            f"camera_shape: controller expects {want_res}, "
            f"environment provides {measured.get('camera_shape')}"
        )
    if abs(controller.control_dt - float(measured.get("control_dt", 0.0))) > 1e-9:
        problems.append(
            f"control_dt: controller expects {controller.control_dt}, "
            f"environment runs at {measured.get('control_dt')}"
        )
    if controller.action_units != measured.get("action_units"):
        problems.append(
            f"action_units: controller emits {controller.action_units!r}, "
            f"environment consumes {measured.get('action_units')!r}"
        )
    return problems
