"""Robot-specific control policies used by the SimulationManager."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

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
    "turtlebot3": RobotInfo(
        "turtlebot3",
        "TurtleBot3 Burger",
        "robotis_turtlebot3_burger",
        "Apache-2.0",
        120.0,
        -22.0,
        0.85,
        (),
    ),
    "go2": RobotInfo(
        "go2",
        "Unitree Go2",
        "unitree_go2",
        "BSD-3-Clause",
        120.0,
        -18.0,
        1.45,
        ("Stand", "Low profile", "High profile"),
    ),
}


def load_robot_model(info: RobotInfo) -> mujoco.MjModel:
    if info.key == "turtlebot3":
        scene = Path(__file__).parent / "models/turtlebot3_burger/scene_turtlebot3_burger.xml"
        return mujoco.MjModel.from_xml_path(str(scene))
    return mujoco_menagerie.load(info.model_id)


def prefetch_models() -> None:
    """Download and compile every pinned showroom model once."""
    from .go2_policy import policy_path
    policy_path()
    for info in ROBOTS.values():
        print(f"fetching {info.label} ...", flush=True)
        model = load_robot_model(info)
        print(f"  ok: {model.nq} qpos, {model.nu} actuators ({info.license})")


class RobotController:
    """Common lifecycle and velocity-command contract for one robot."""

    def __init__(self, info: RobotInfo):
        self.info = info
        self.model = load_robot_model(info)
        self.data = mujoco.MjData(self.model)
        self.automatic = True
        self.motion_vx = 0.0
        self.motion_vy = 0.0
        self.motion_wz = 0.0
        self.speed = 1.0
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

    def set_motion(self, vx: float, wz: float, speed: float, vy: float = 0.0) -> None:
        self.automatic = False
        self.motion_vx = float(np.clip(vx, -1.0, 1.0))
        self.motion_vy = float(np.clip(vy, -1.0, 1.0))
        self.motion_wz = float(np.clip(wz, -1.0, 1.0))
        self.speed = float(np.clip(speed, 0.1, 1.0))

    def stop(self) -> None:
        self.motion_vx = 0.0
        self.motion_vy = 0.0
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


class TurtleBotController(RobotController):
    """Body velocity to wheel velocity using ROBOTIS's Burger geometry."""

    WHEEL_RADIUS = 0.033
    WHEEL_SEPARATION = 0.160
    MAX_LINEAR_SPEED = 0.22
    MAX_YAW_RATE = 1.5

    def _reset_controller(self) -> None:
        self._wheel_ids = np.array([
            self.model.actuator("wheel_left").id,
            self.model.actuator("wheel_right").id,
        ])
        self.automatic = False
        self.stop()

    def _apply_control(self) -> None:
        linear = self.MAX_LINEAR_SPEED * self.speed * self.motion_vx
        angular = self.MAX_YAW_RATE * self.speed * self.motion_wz
        wheels = np.array([
            linear - angular * self.WHEEL_SEPARATION / 2,
            linear + angular * self.WHEEL_SEPARATION / 2,
        ]) / self.WHEEL_RADIUS
        # Scale both wheels together to preserve curvature at actuator limits.
        limits = self.model.actuator_ctrlrange[self._wheel_ids, 1]
        wheels /= max(1.0, float(np.max(np.abs(wheels) / limits)))
        self.data.ctrl[self._wheel_ids] = wheels


class Go2Controller(RobotController):
    """CPU walking policy with explicit stationary posture transitions."""

    def _reset_controller(self) -> None:
        from .go2_policy import Go2Policy, DEFAULT_ANGLES
        if not hasattr(self, "policy"):
            self.policy = Go2Policy()
        self.policy.reset()
        # Match the deployment model's passive joint dynamics and calf limits.
        # Menagerie's default damping=2 would fight this policy's kd=0.5.
        self.model.opt.timestep = .002
        self.model.dof_damping[6:] = .001
        self.model.dof_frictionloss[6:] = .1
        self.model.actuator_ctrlrange[2::3] = [-35.55, 35.55]
        self.home = DEFAULT_ANGLES.copy()
        self.target = self.home.copy()
        self.profile = "Stand"
        self._pending_profile = None
        self._settle_until = 0.0
        self._counter = 0
        self._pose_start = self.home.copy()
        self._pose_time = 0.0
        self.automatic = False
        self.stop()

    def set_motion(self, vx: float, wz: float, speed: float, vy: float = 0.0) -> None:
        super().set_motion(vx, wz, speed, vy)
        # Walking always uses the policy's trained height. Postures are stationary.
        if max(abs(vx), abs(vy), abs(wz)) > 0 and (
            self.profile != "Stand" or self._pending_profile is not None
        ):
            self.profile = "Stand"
            self._pending_profile = None
            self.policy.reset()
            self._counter = 0

    def action(self, name: str) -> bool:
        if name not in self.info.actions:
            return False
        self.stop()
        if name == "Stand":
            self.profile = name
            self._pending_profile = None
            self.policy.reset()
            self._counter = 0
        elif name != self.profile and name != self._pending_profile:
            # Let zero-velocity policy settle before transitioning to posture PD.
            self._pending_profile = name
            self._settle_until = self.data.time + (.8 if self.profile == "Stand" else 0)
        return True

    def _apply_control(self) -> None:
        if self._pending_profile and self.data.time >= self._settle_until:
            self.profile = self._pending_profile
            self._pending_profile = None
            self._pose_start = self.data.qpos[7:].copy()
            self._pose_time = self.data.time
        if self.profile == "Stand":
            if self._counter % 10 == 0:
                command = self.speed * np.array([
                    .5 * self.motion_vx, .35 * self.motion_vy, .8 * self.motion_wz
                ])
                self.target = self.policy.target(self.data, command)
            self._counter += 1
            kp, kd = 20., .5
        else:
            # Interpolate between Unitree's documented FixStand poses.
            # These are stationary joint targets, not a fabricated walking gait.
            high = np.tile([0., .8, -1.5], 4)
            low = np.tile([0., 1.36, -2.65], 4)
            goal = high if self.profile == "High profile" else .6 * low + .4 * high
            alpha = min(1., (self.data.time - self._pose_time) / 1.2)
            alpha = alpha * alpha * (3 - 2 * alpha)
            self.target = (1-alpha) * self._pose_start + alpha * goal
            kp, kd = 60., 4.
        self.target = np.clip(self.target, self.model.jnt_range[1:, 0], self.model.jnt_range[1:, 1])
        torque = kp * (self.target - self.data.qpos[7:]) - kd * self.data.qvel[6:]
        ranges = self.model.actuator_ctrlrange
        self.data.ctrl[:] = np.clip(torque, ranges[:, 0], ranges[:, 1])


def create_controller(name: str) -> RobotController:
    info = ROBOTS[name]
    if name == "panda":
        return PandaController(info)
    if name == "turtlebot3":
        return TurtleBotController(info)
    if name == "go2":
        return Go2Controller(info)
    raise KeyError(name)
