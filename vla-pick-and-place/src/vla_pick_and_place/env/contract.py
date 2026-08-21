"""The observation/action contract, captured from the live environment.

`EXPECTED` is not documentation — it is the Phase 0 measurement of the pinned
`so101-nexus==0.5.1` `MuJoCoPickAndPlace-v1`, written down so that a version
bump that changes the schema fails a test instead of quietly changing what the
dashboard is labelling. `capture()` re-measures; `diff()` reports field-level
mismatches by name, which is what both the env test and the controller
compatibility check need.

Every value here was produced by `python -m vla_pick_and_place.run contract`
on macOS 26.5 / arm64 / Python 3.12 / mujoco 3.10 and is reproducible with it.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from vla_pick_and_place.config import (
    CAMERA_H,
    CAMERA_W,
    CONTROL_DT,
    ENV_ID,
    MAX_EPISODE_STEPS,
    N_JOINTS,
    OBS_ENV_STATE,
    OBS_OVERHEAD,
    OBS_STATE,
    OBS_WRIST,
)

# Flat privileged state vector: JointPositions(6) JointVelocities(6)
# EndEffectorPose(7) GraspState(1) GazeState(1) TargetPosition(3)
# ObjectPose(7) ObjectVelocity(6) ObjectOffset(3) TargetOffset(3).
ENV_STATE_DIM = 43

# Offsets into that vector, in the component order above. Read once from
# upstream's own `privileged_state_feature_names` and asserted in the env test,
# so a component-order change upstream fails loudly instead of silently
# renaming what the expert reads.
JOINT_POSITIONS_INDEX = 0
JOINT_VELOCITIES_INDEX = 6
END_EFFECTOR_POSE_INDEX = 12
GRASP_STATE_INDEX = 19
GAZE_STATE_INDEX = 20
TARGET_POSITION_INDEX = 21
OBJECT_POSE_INDEX = 24
OBJECT_VELOCITY_INDEX = 31
OBJECT_OFFSET_INDEX = 37
TARGET_OFFSET_INDEX = 40

STATE_INDICES = {
    "joint_positions_0": JOINT_POSITIONS_INDEX,
    "joint_velocities_0": JOINT_VELOCITIES_INDEX,
    "end_effector_pose_0": END_EFFECTOR_POSE_INDEX,
    "grasp_state_0": GRASP_STATE_INDEX,
    "gaze_state_0": GAZE_STATE_INDEX,
    "target_position_0": TARGET_POSITION_INDEX,
    "object_pose_0": OBJECT_POSE_INDEX,
    "object_velocity_0": OBJECT_VELOCITY_INDEX,
    "object_offset_0": OBJECT_OFFSET_INDEX,
    "target_offset_0": TARGET_OFFSET_INDEX,
}

# Upstream's action space is absolute joint position in RADIANS, one per
# actuator, bounded by the actuator control range. These are the measured
# bounds at FULL float32 precision — deliberately not rounded for readability.
# They are also the reason a dataset row (degrees + gripper percent) cannot be
# fed to `step()` without the published unit conversion.
ACTION_LOW = (
    -1.9198600053787231,
    -1.7453292608261108,
    -1.6900000572204590,
    -1.6580599546432495,
    -2.7438473701477050,
    -0.1745299994945526,
)
ACTION_HIGH = (
    1.9198600053787231,
    1.7453292608261108,
    1.6900000572204590,
    1.6580599546432495,
    2.7438473701477050,
    1.7453291416168213,
)


def clamp_to_action_range(values, low=ACTION_LOW, high=ACTION_HIGH) -> list[float]:
    """Clip a joint vector into `[low, high]`, defaulting to the actuator range.

    Needed because a reset joint POSITION is not guaranteed to be inside the
    actuator CONTROL range: upstream resets with `robot_init_qpos_noise`, so a
    joint parked at its limit can settle a hair outside it — the gripper comes
    back at -0.17454 against a -0.17453 lower bound. Feeding that straight
    into a slider is a hard client-side error ("Value ... is less than minimum
    value ..."), which is how this surfaced.

    `low`/`high` are parameters rather than fixed, because the UI's sliders
    round the bounds INWARD for display: a value clamped to the true range can
    still sit outside the rounded one, so a caller clamping for a slider has
    to clamp to that slider's own bounds.
    """
    return [
        float(min(max(float(v), lo), hi)) for v, lo, hi in zip(values, low, high)
    ]

# Keys `info` carries on every reset and step. `success` is the success
# predicate; the rest are the shaping/diagnostic terms the UI can show.
INFO_KEYS = (
    "is_grasped",
    "is_obj_placed",
    "is_obj_static",
    "is_robot_static",
    "lift_height",
    "obj_to_target_dist",
    "success",
    "target_index",
    "target_object",
    "task_potential",
    "tcp_to_obj_dist",
)
SUCCESS_KEY = "success"

EXPECTED: dict[str, Any] = {
    "env_id": ENV_ID,
    "max_episode_steps": MAX_EPISODE_STEPS,
    "control_dt": CONTROL_DT,
    "action_shape": [N_JOINTS],
    "action_dtype": "float32",
    "action_units": "radians (absolute joint position, pd_joint_pos)",
    "observation_keys": sorted([OBS_STATE, OBS_ENV_STATE, OBS_WRIST, OBS_OVERHEAD]),
    "state_shape": [N_JOINTS],
    "environment_state_shape": [ENV_STATE_DIM],
    "camera_shape": [CAMERA_H, CAMERA_W, 3],
    "camera_dtype": "uint8",
    "info_keys": sorted(INFO_KEYS),
    "success_key": SUCCESS_KEY,
}


def capture(env=None) -> dict[str, Any]:
    """Measure the live environment's contract. Builds one if not given."""
    from vla_pick_and_place.env.nexus import NexusPickAndPlace

    own = env is None
    env = env or NexusPickAndPlace()
    try:
        obs, info = env.reset(seed=0)
        space = env.action_space
        return {
            "env_id": ENV_ID,
            "max_episode_steps": env.max_episode_steps,
            "control_dt": round(env.control_dt, 6),
            "action_shape": list(space.shape),
            "action_dtype": str(space.dtype),
            "action_units": EXPECTED["action_units"],
            "observation_keys": sorted(obs.keys()),
            "state_shape": list(np.asarray(obs[OBS_STATE]).shape),
            "environment_state_shape": list(np.asarray(obs[OBS_ENV_STATE]).shape),
            "camera_shape": list(np.asarray(obs[OBS_WRIST]).shape),
            "camera_dtype": str(np.asarray(obs[OBS_WRIST]).dtype),
            "info_keys": sorted(info.keys()),
            "success_key": SUCCESS_KEY,
        }
    finally:
        if own:
            env.close()


def diff(measured: dict[str, Any], expected: dict[str, Any] | None = None) -> list[str]:
    """Field-level mismatches, newest measurement first in each message.

    Returns an empty list when the contract holds. Messages name the field and
    both values, because "schema mismatch" without the field name is the error
    message this migration exists to stop shipping.
    """
    expected = EXPECTED if expected is None else expected
    problems: list[str] = []
    for field, want in expected.items():
        if field not in measured:
            problems.append(f"{field}: missing from the measured contract (expected {want!r})")
            continue
        got = measured[field]
        if isinstance(want, float) and isinstance(got, (int, float)):
            mismatch = abs(float(got) - want) > 1e-9
        elif isinstance(want, (list, tuple)):
            mismatch = list(got) != list(want)
        else:
            mismatch = got != want
        if mismatch:
            problems.append(f"{field}: measured {got!r}, expected {want!r}")
    return problems


def check(env=None) -> dict[str, Any]:
    """Capture and verify in one call. Raises `ContractError` on mismatch."""
    measured = capture(env)
    problems = diff(measured)
    if problems:
        raise ContractError(
            "the pinned SO101-Nexus environment no longer matches the recorded "
            "contract:\n  - " + "\n  - ".join(problems)
        )
    return measured


class ContractError(RuntimeError):
    """The live environment disagrees with the contract this app was built on."""
