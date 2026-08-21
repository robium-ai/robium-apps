"""Thin adapter over the published SO101-Nexus `MuJoCoPickAndPlace-v1`.

This app used to own its physics: a hand-built MJCF scene, a damped-least-
squares IK solver, a calibrated grasp offset, and a bespoke success predicate.
All of it is gone. so101-nexus publishes the same robot in the same simulator
with golden-trajectory regression tests, LeRobot-compatible recording, and a
documented stability contract, so the app's job is now *translation*, not
simulation.

Deliberately narrow. This class does five things:

  * construct the pinned env with the camera observations the demo needs,
  * reset it from a seed,
  * rename upstream's observation keys onto LeRobot's,
  * pass reward / terminated / truncated / success through untouched,
  * close render resources on the thread that made them.

What it must NOT do, and what upstream owns instead: a success predicate (use
`info["success"]`), an action-unit convention (upstream's radians go through
verbatim), a scene tweak, or a resized camera frame. Every one of those is a
place where "the app's environment" could drift away from "the environment the
published datasets and checkpoints were recorded in", which is the exact
failure this migration undid.

Threading: MuJoCo's GL context is thread-affine — CGL on macOS especially.
An env built on one thread and rendered from another DEADLOCKS in
`make_current` with no error, which this app has hit for real. Build, step,
and close on one thread; `demo/session.py` constructs a fresh env inside each
request rather than sharing one.
"""

from __future__ import annotations

import os
from typing import Any

import numpy as np

from vla_pick_and_place.config import (
    CAMERA_H,
    CAMERA_W,
    ENV_ID,
    OBS_ENV_STATE,
    OBS_OVERHEAD,
    OBS_STATE,
    OBS_WRIST,
)


def set_gl_backend() -> str:
    """Pick MuJoCo's GL backend if the caller has not. Returns the value used.

    Not optional and not auto-detected by MuJoCo: CGL on macOS, EGL on Linux.
    Getting it wrong is a hang or a blank render, not an exception. Must run
    before the first `import mujoco`, so every entry point calls this first.
    """
    if not os.environ.get("MUJOCO_GL"):
        import sys

        os.environ["MUJOCO_GL"] = "cgl" if sys.platform == "darwin" else "egl"
    return os.environ["MUJOCO_GL"]


class NexusPickAndPlace:
    """`MuJoCoPickAndPlace-v1` with wrist + overhead cameras, LeRobot key names."""

    def __init__(
        self,
        *,
        camera_w: int = CAMERA_W,
        camera_h: int = CAMERA_H,
        control_mode: str = "pd_joint_pos",
        cameras: bool = True,
    ):
        """`control_mode` is upstream's own; `cameras=False` skips rendering.

        The demo and every policy use `pd_joint_pos` — absolute joint radians,
        the app's declared action contract. The scripted expert asks for
        `pd_ee_pose` instead so that UPSTREAM solves the IK; it still records
        the joint targets the environment derived (see
        `commanded_joint_targets`), so the data it produces stays on the
        joint-space contract.

        `cameras=False` drops both camera observations. Only for headless
        expert sweeps: rendering is ~half the step cost and a success-rate
        sweep looks at `info`, not pixels.
        """
        set_gl_backend()

        import gymnasium as gym
        import so101_nexus.mujoco  # noqa: F401  — registers the MuJoCo env ids
        from so101_nexus.config import PickAndPlaceConfig
        from so101_nexus.observations import (
            JointPositions,
            OverheadCamera,
            WristCamera,
            component_slice,
            privileged_state_feature_names,
        )

        config = PickAndPlaceConfig()
        # Append rather than replace: the default component list IS the
        # published observation contract (and what the maintainer's dataset
        # recorded), so the state vector keeps its documented layout and only
        # the two cameras are added.
        if cameras:
            config.observations = list(config.observations) + [
                WristCamera(width=camera_w, height=camera_h),
                OverheadCamera(width=camera_w, height=camera_h),
            ]

        self._env = gym.make(
            ENV_ID, config=config, render_mode="rgb_array", control_mode=control_mode
        )
        self.control_mode = control_mode
        self.has_cameras = cameras
        self._components = config.observations
        # The first 6 dims of the flat state vector are joint positions. Read
        # the slice from upstream's own helper instead of hardcoding 0:6, so a
        # component-order change upstream surfaces as a different slice rather
        # than as silently mislabelled numbers.
        self._joint_slice = component_slice(self._components, JointPositions)
        self.state_feature_names = privileged_state_feature_names(self._components)
        self.camera_w = camera_w
        self.camera_h = camera_h
        self._closed = False

    # --- upstream passthrough ------------------------------------------------

    @property
    def env(self):
        """The wrapped Gymnasium env, for callers that need the raw handle."""
        return self._env

    @property
    def action_space(self):
        return self._env.action_space

    @property
    def max_episode_steps(self) -> int:
        return int(self._env.spec.max_episode_steps)

    @property
    def control_dt(self) -> float:
        """Simulated seconds per `step()`, straight off the unwrapped env."""
        return float(self._env.unwrapped.control_dt)

    def zero_action(self) -> np.ndarray:
        return np.zeros(self.action_space.shape, dtype=np.float32)

    def hold_action(self, obs: dict[str, Any]) -> np.ndarray:
        """The action that commands the arm to stay where it is.

        Control is absolute joint position (`pd_joint_pos`), so "hold" is the
        current joint vector, not zeros — zeros command the zero pose and drop
        the arm. Used by the explore mode's idle frames.
        """
        return np.asarray(obs[OBS_STATE], dtype=np.float32)

    # --- normalized surface --------------------------------------------------

    def commanded_joint_targets(self) -> np.ndarray:
        """The six joint position targets the env last sent to the actuators.

        MuJoCo's `data.ctrl` holds them whatever the control mode, so this
        reads the SAME quantity a `pd_joint_pos` action would have been. That
        is what makes an expert driven in TCP space able to record actions the
        joint-space demo can replay.
        """
        u = self._env.unwrapped
        return np.asarray(u.data.ctrl[u._actuator_ids], dtype=np.float32).copy()

    def _observation(self, raw: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        """Rename upstream's observation onto LeRobot's key names.

        No resizing, no dtype games, no copies beyond the slice: camera frames
        are handed on as the uint8 HWC arrays upstream rendered.
        """
        if not self.has_cameras:
            state = np.asarray(raw, dtype=np.float32)
            return {OBS_STATE: state[self._joint_slice], OBS_ENV_STATE: state}
        state = np.asarray(raw["state"], dtype=np.float32)
        return {
            OBS_STATE: state[self._joint_slice],
            OBS_ENV_STATE: state,
            OBS_WRIST: raw["wrist_camera"],
            OBS_OVERHEAD: raw["overhead_camera"],
        }

    def reset(self, seed: int | None = None) -> tuple[dict[str, np.ndarray], dict]:
        raw, info = self._env.reset(seed=seed)
        return self._observation(raw), dict(info)

    def step(self, action) -> tuple[dict[str, np.ndarray], float, bool, bool, dict]:
        action = np.asarray(action, dtype=np.float32)
        raw, reward, terminated, truncated, info = self._env.step(action)
        return (
            self._observation(raw),
            float(reward),
            bool(terminated),
            bool(truncated),
            dict(info),
        )

    def render(self) -> np.ndarray:
        """The env's own third-person render view (not a camera observation)."""
        return np.asarray(self._env.render())

    def close(self) -> None:
        if not self._closed:
            self._env.close()
            self._closed = True

    def __enter__(self) -> NexusPickAndPlace:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()


def success_of(info: dict) -> bool:
    """Upstream's success flag. There is no app-owned success predicate.

    Kept as a named function so the one place that reads the key is greppable
    if upstream ever renames it — and so nothing is tempted to re-derive
    "success" from positions, which is how the previous implementation grew a
    500-line calibration comment.
    """
    return bool(info["success"])
