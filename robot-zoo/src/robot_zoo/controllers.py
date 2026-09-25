"""Robot-specific control policies used by the SimulationManager."""

from __future__ import annotations

import math
from dataclasses import dataclass

import mujoco
import mujoco_menagerie
import numpy as np


@dataclass(frozen=True)
class RobotInfo:
    key: str
    label: str
    model_id: str
    license: str
    camera_azimuth: float
    camera_elevation: float
    camera_distance: float
    actions: tuple[str, ...]


ROBOTS: dict[str, RobotInfo] = {
    "panda": RobotInfo(
        "panda",
        "Franka Panda",
        "franka_emika_panda",
        "Apache-2.0",
        135.0,
        -22.0,
        1.35,
        ("Raise", "Lower", "Open gripper", "Close gripper"),
    ),
    "stretch": RobotInfo(
        "stretch",
        "Hello Robot Stretch 3",
        "hello_robot_stretch_3",
        "Apache-2.0",
        -55.0,
        -18.0,
        1.75,
        ("Lift up", "Lift down", "Extend", "Retract"),
    ),
    "go2": RobotInfo(
        "go2",
        "Unitree Go2",
        "unitree_go2",
        "BSD-3-Clause",
        120.0,
        -18.0,
        1.45,
        ("Stand", "Sit"),
    ),
}


def prefetch_models() -> None:
    """Download and compile every pinned showroom model once."""
    for info in ROBOTS.values():
        print(f"fetching {info.label} ...", flush=True)
        model = mujoco_menagerie.load(info.model_id)
        print(f"  ok: {model.nq} qpos, {model.nu} actuators ({info.license})")


class RobotController:
    """Common lifecycle and velocity-command contract for one robot."""

    def __init__(self, info: RobotInfo):
        self.info = info
        self.model = mujoco_menagerie.load(info.model_id)
        self.data = mujoco.MjData(self.model)
        self.automatic = True
        self.motion_vx = 0.0
        self.motion_wz = 0.0
        self.speed = 0.5
        self.reset()

    def reset(self) -> None:
        if self.model.nkey:
            mujoco.mj_resetDataKeyframe(self.model, self.data, 0)
        else:
            mujoco.mj_resetData(self.model, self.data)
        mujoco.mj_forward(self.model, self.data)
        self._reset_controller()

    def reset_to_demo(self) -> None:
        self.stop()
        self.automatic = True
        self.reset()

    def set_motion(self, vx: float, wz: float, speed: float) -> None:
        self.automatic = False
        self.motion_vx = float(np.clip(vx, -1.0, 1.0))
        self.motion_wz = float(np.clip(wz, -1.0, 1.0))
        self.speed = float(np.clip(speed, 0.1, 1.0))

    def stop(self) -> None:
        self.motion_vx = 0.0
        self.motion_wz = 0.0

    def action(self, name: str) -> bool:
        return False

    def step(self) -> None:
        self._apply_control()
        mujoco.mj_step(self.model, self.data)

    def _reset_controller(self) -> None:
        pass

    def _apply_control(self) -> None:
        raise NotImplementedError


class PandaController(RobotController):
    def _reset_controller(self) -> None:
        self._hand_id = self.model.body("hand").id
        self._joint_ids = np.array(
            [self.model.joint(f"joint{i}").id for i in range(1, 8)]
        )
        self._qpos_ids = self.model.jnt_qposadr[self._joint_ids]
        self._dof_ids = self.model.jnt_dofadr[self._joint_ids]
        self._actuator_ids = np.arange(7)
        self._jacobian = np.zeros((3, self.model.nv))
        self.target = self.data.xpos[self._hand_id].copy()
        self.gripper = float(self.data.ctrl[7])

    def action(self, name: str) -> bool:
        self.automatic = False
        if name == "Raise":
            self.target[2] = min(0.85, self.target[2] + 0.05)
        elif name == "Lower":
            self.target[2] = max(0.20, self.target[2] - 0.05)
        elif name == "Open gripper":
            self.gripper = 255.0
        elif name == "Close gripper":
            self.gripper = 0.0
        else:
            return False
        return True

    def _apply_control(self) -> None:
        if self.automatic:
            t = self.data.time
            self.target[:] = (
                0.50 + 0.07 * math.cos(0.8 * t),
                0.20 * math.sin(0.8 * t),
                0.56 + 0.07 * math.sin(0.4 * t),
            )
            self.gripper = 127.5 + 127.5 * math.sin(0.8 * t)
        else:
            dt = self.model.opt.timestep
            self.target += dt * 0.20 * self.speed * np.array(
                [self.motion_vx, self.motion_wz, 0.0]
            )
            self.target[:] = np.clip(
                self.target,
                np.array([0.25, -0.38, 0.20]),
                np.array([0.72, 0.38, 0.85]),
            )

        mujoco.mj_jacBody(
            self.model, self.data, self._jacobian, None, self._hand_id
        )
        jac = self._jacobian[:, self._dof_ids]
        error = self.target - self.data.xpos[self._hand_id]
        damping = 0.035
        velocity = jac.T @ np.linalg.solve(
            jac @ jac.T + (damping**2) * np.eye(3), 4.0 * error
        )
        position_target = self.data.qpos[self._qpos_ids] + 0.055 * np.clip(
            velocity, -1.4, 1.4
        )
        ranges = self.model.actuator_ctrlrange[self._actuator_ids]
        self.data.ctrl[self._actuator_ids] = np.clip(
            position_target, ranges[:, 0], ranges[:, 1]
        )
        self.data.ctrl[7] = float(np.clip(self.gripper, 0.0, 255.0))


class StretchController(RobotController):
    def action(self, name: str) -> bool:
        self.automatic = False
        if name == "Lift up":
            self.data.ctrl[2] = np.clip(self.data.ctrl[2] + 0.08, 0.0, 1.1)
        elif name == "Lift down":
            self.data.ctrl[2] = np.clip(self.data.ctrl[2] - 0.08, 0.0, 1.1)
        elif name == "Extend":
            self.data.ctrl[3] = np.clip(self.data.ctrl[3] + 0.06, 0.0, 0.52)
        elif name == "Retract":
            self.data.ctrl[3] = np.clip(self.data.ctrl[3] - 0.06, 0.0, 0.52)
        else:
            return False
        return True

    def _apply_control(self) -> None:
        if self.automatic:
            t = self.data.time
            self.data.ctrl[0] = 0.75 * math.sin(0.55 * t)
            self.data.ctrl[1] = -0.75 * math.sin(0.55 * t)
            self.data.ctrl[2] = 0.62 + 0.22 * (0.5 + 0.5 * math.sin(0.65 * t))
            self.data.ctrl[3] = 0.10 + 0.22 * (0.5 + 0.5 * math.sin(0.45 * t))
            self.data.ctrl[8] = 0.65 * math.sin(0.75 * t)
            self.data.ctrl[9] = -0.35 + 0.12 * math.sin(0.55 * t)
            return

        self.data.ctrl[0] = self.speed * (
            -2.0 * self.motion_vx - 1.5 * self.motion_wz
        )
        self.data.ctrl[1] = self.speed * (
            2.0 * self.motion_vx - 1.5 * self.motion_wz
        )


class Go2Controller(RobotController):
    def _reset_controller(self) -> None:
        names = (
            "FL_hip_joint",
            "FL_thigh_joint",
            "FL_calf_joint",
            "FR_hip_joint",
            "FR_thigh_joint",
            "FR_calf_joint",
            "RL_hip_joint",
            "RL_thigh_joint",
            "RL_calf_joint",
            "RR_hip_joint",
            "RR_thigh_joint",
            "RR_calf_joint",
        )
        self._joint_ids = np.array([self.model.joint(name).id for name in names])
        self._qpos_ids = self.model.jnt_qposadr[self._joint_ids]
        self._dof_ids = self.model.jnt_dofadr[self._joint_ids]
        self.home = self.data.qpos[self._qpos_ids].copy()
        self.target = self.home.copy()
        self.crouch = 0.0
        self.sway = 0.0

    def action(self, name: str) -> bool:
        self.automatic = False
        if name == "Stand":
            self.crouch = 0.0
        elif name == "Sit":
            self.crouch = 0.34
        else:
            return False
        return True

    def _apply_control(self) -> None:
        if self.automatic:
            t = self.data.time
            self.crouch = 0.16 * (0.5 + 0.5 * math.sin(0.85 * t))
            self.sway = 0.06 * math.sin(0.55 * t)
        else:
            dt = self.model.opt.timestep
            self.crouch = float(
                np.clip(
                    self.crouch - dt * 0.60 * self.speed * self.motion_vx,
                    0.0,
                    0.38,
                )
            )
            self.sway = float(
                np.clip(
                    self.sway + dt * 0.35 * self.speed * self.motion_wz,
                    -0.18,
                    0.18,
                )
            )

        self.target[:] = self.home
        self.target[1::3] += self.crouch
        self.target[2::3] -= 2.0 * self.crouch
        self.target[[0, 6]] += self.sway
        self.target[[3, 9]] -= self.sway

        position = self.data.qpos[self._qpos_ids]
        velocity = self.data.qvel[self._dof_ids]
        torque = 80.0 * (self.target - position) - 3.0 * velocity
        ranges = self.model.actuator_ctrlrange
        self.data.ctrl[:] = np.clip(torque, ranges[:, 0], ranges[:, 1])


def create_controller(name: str) -> RobotController:
    info = ROBOTS[name]
    if name == "panda":
        return PandaController(info)
    if name == "stretch":
        return StretchController(info)
    if name == "go2":
        return Go2Controller(info)
    raise KeyError(name)
