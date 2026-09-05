"""MuJoCo push arena.

Give it a normalized (throttle, steer) action at the control rate, get back an
overhead RGB frame. Nothing else crosses the boundary: the recording and
training layers see only images and actions.
"""

from __future__ import annotations

import os
import platform
from pathlib import Path

import numpy as np

# macOS has exactly one headless GL backend, and it must be chosen before the
# module is imported. osmesa and egl are Linux-only.
if platform.system() == "Darwin":
    os.environ.setdefault("MUJOCO_GL", "cgl")

import mujoco  # noqa: E402

from ..config import CONTROL_HZ, mix  # noqa: E402

SCENE_PATH = Path(__file__).parent / "scene.xml"

# Wheel speed at full throttle. 8 rad/s on 30 mm wheels is about 0.24 m/s,
# slow enough that a 1 m pen takes a few seconds to cross. At the actuator's
# full 20 rad/s the robot crossed the arena in under two seconds, which is
# neither controllable by hand nor useful to learn from.
MAX_WHEEL_RAD_S = 8.0


class PushEnv:
    """A robot, a block, and a painted goal, seen from overhead.

    The renderer is constructed here and used only from the calling thread: on
    macOS the CGL backend is thread-affine, and a first render from a different
    thread deadlocks silently with no error and no timeout.
    """

    def __init__(self, render_size: int = 256, seed: int | None = None):
        self.model = mujoco.MjModel.from_xml_path(str(SCENE_PATH))
        self.data = mujoco.MjData(self.model)
        self.render_size = render_size
        self._renderer = mujoco.Renderer(self.model, height=render_size, width=render_size)
        self._rng = np.random.default_rng(seed)

        self._steps_per_action = max(1, int(round(1.0 / (CONTROL_HZ * self.model.opt.timestep))))
        self._settle_steps = int(round(1.0 / self.model.opt.timestep))
        self._chassis_qpos = self._freejoint_address("chassis_free")
        self._block_qpos = self._freejoint_address("block_free")

        # A fresh Renderer's first reset -> mj_forward -> render cycle does not
        # reproduce against later renders. Burn it here so recorded episodes and
        # evaluation runs agree frame for frame.
        self._warm_up()

    def _freejoint_address(self, name: str) -> int:
        joint_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, name)
        return int(self.model.jnt_qposadr[joint_id])

    def _warm_up(self) -> None:
        mujoco.mj_resetData(self.model, self.data)
        mujoco.mj_forward(self.model, self.data)
        self._renderer.update_scene(self.data, camera="overhead")
        self._renderer.render()

    def reset(self, seed: int | None = None) -> np.ndarray:
        """Randomize the starting layout and return the first observation."""
        if seed is not None:
            self._rng = np.random.default_rng(seed)

        mujoco.mj_resetData(self.model, self.data)

        # Robot starts behind the block, roughly facing it.
        yaw = float(self._rng.uniform(-0.5, 0.5))
        self._set_pose(
            self._chassis_qpos,
            x=float(self._rng.uniform(-0.42, -0.22)),
            y=float(self._rng.uniform(-0.20, 0.20)),
            z=0.035,
            yaw=yaw,
        )
        # Block starts between the robot and the goal.
        self._set_pose(
            self._block_qpos,
            x=float(self._rng.uniform(-0.10, 0.12)),
            y=float(self._rng.uniform(-0.14, 0.14)),
            z=0.030,
            yaw=float(self._rng.uniform(-np.pi, np.pi)),
        )

        mujoco.mj_forward(self.model, self.data)

        # Let the drop settle before the episode starts. Bodies are placed at
        # their exact resting height, but contact resolution still nudges them a
        # few millimetres over the first second - motion no action explains, and
        # therefore noise a behaviour-cloning policy would try to account for.
        self.data.ctrl[:] = 0.0
        for _ in range(self._settle_steps):
            mujoco.mj_step(self.model, self.data)

        return self.observe()

    def _set_pose(self, address: int, x: float, y: float, z: float, yaw: float) -> None:
        self.data.qpos[address : address + 3] = (x, y, z)
        self.data.qpos[address + 3 : address + 7] = (
            np.cos(yaw / 2.0),
            0.0,
            0.0,
            np.sin(yaw / 2.0),
        )

    def step(self, action: np.ndarray | tuple[float, float]) -> np.ndarray:
        """Apply one control-rate action and return the resulting observation."""
        left, right = mix(action)
        self.data.ctrl[0] = left * MAX_WHEEL_RAD_S
        self.data.ctrl[1] = right * MAX_WHEEL_RAD_S

        for _ in range(self._steps_per_action):
            mujoco.mj_step(self.model, self.data)

        return self.observe()

    def observe(self) -> np.ndarray:
        """Overhead RGB frame - the policy's entire view of the world."""
        self._renderer.update_scene(self.data, camera="overhead")
        return self._renderer.render()

    # --- interactive scene setting -------------------------------------------------
    #
    # Placing objects by hand is how the real rig will work: you put the block
    # somewhere, point the robot roughly at it, and let the policy go. These
    # helpers exist so the simulator supports the same loop.

    def place_robot(self, x: float, y: float, yaw: float | None = None) -> None:
        """Teleport the robot. Keeps its heading unless ``yaw`` is given."""
        if yaw is None:
            yaw = self.robot_yaw()
        self._set_pose(self._chassis_qpos, x, y, 0.035, yaw)
        self._zero_velocity(self._chassis_qpos)
        mujoco.mj_forward(self.model, self.data)

    def place_block(self, x: float, y: float, yaw: float | None = None) -> None:
        """Teleport the block, dropping any momentum it had."""
        if yaw is None:
            yaw = self.block_yaw()
        self._set_pose(self._block_qpos, x, y, 0.030, yaw)
        self._zero_velocity(self._block_qpos)
        mujoco.mj_forward(self.model, self.data)

    def _zero_velocity(self, qpos_address: int) -> None:
        """Clear a free joint's velocity so a teleport does not fling the body.

        A free joint contributes 7 qpos entries but only 6 qvel entries, so the
        velocity offset is not the same number as the position offset.
        """
        joint_id = int(np.argmax(self.model.jnt_qposadr == qpos_address))
        address = int(self.model.jnt_dofadr[joint_id])
        self.data.qvel[address : address + 6] = 0.0

    def robot_yaw(self) -> float:
        return self._yaw(self._chassis_qpos)

    def block_yaw(self) -> float:
        return self._yaw(self._block_qpos)

    def _yaw(self, address: int) -> float:
        w, _, _, z = self.data.qpos[address + 3 : address + 7]
        return float(2.0 * np.arctan2(z, w))

    def settle(self, seconds: float = 0.2) -> None:
        """Let contacts resolve with the motors off, without an action."""
        self.data.ctrl[:] = 0.0
        for _ in range(int(seconds / self.model.opt.timestep)):
            mujoco.mj_step(self.model, self.data)

    def pixel_to_world(self, u: float, v: float, height: float = 0.030) -> np.ndarray:
        """Map a pixel in the rendered frame to a point on a horizontal plane.

        The overhead camera looks straight down, so a pixel corresponds to
        exactly one world point once the plane's height is fixed - no ray
        casting needed.
        """
        cam_x, cam_y, cam_z, half_w, half_h = self._camera_extent(height)
        size = self.render_size
        ndc_x = (u + 0.5) / size * 2.0 - 1.0
        # Image rows increase downwards while the camera's y axis points up.
        ndc_y = 1.0 - (v + 0.5) / size * 2.0
        return np.array([cam_x + ndc_x * half_w, cam_y + ndc_y * half_h])

    def world_to_pixel(self, x: float, y: float, height: float = 0.030) -> np.ndarray:
        """Inverse of :meth:`pixel_to_world`."""
        cam_x, cam_y, cam_z, half_w, half_h = self._camera_extent(height)
        size = self.render_size
        ndc_x = (x - cam_x) / half_w
        ndc_y = (y - cam_y) / half_h
        return np.array([(ndc_x + 1.0) / 2.0 * size - 0.5, (1.0 - ndc_y) / 2.0 * size - 0.5])

    def _camera_extent(self, height: float):
        camera_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_CAMERA, "overhead")
        cam_x, cam_y, cam_z = self.model.cam_pos[camera_id]
        fovy = float(self.model.cam_fovy[camera_id])
        half_h = (cam_z - height) * np.tan(np.radians(fovy) / 2.0)
        # The render is square, so horizontal and vertical extents match.
        return float(cam_x), float(cam_y), float(cam_z), half_h, half_h

    def body_xy(self, name: str) -> np.ndarray:
        """World position of a body. Diagnostics only; never a policy input."""
        body_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, name)
        return np.array(self.data.xpos[body_id][:2])

    def close(self) -> None:
        self._renderer.close()

    def __enter__(self) -> PushEnv:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
