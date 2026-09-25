"""Thread-safe simulation ownership for Gradio and MuJoCo."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import numpy as np

from .controllers import ROBOTS, RobotController, create_controller
from .desktop import configure_mujoco_viewer


@dataclass(frozen=True)
class SimulationState:
    active_robot: str
    requested_robot: str | None
    vx: float
    wz: float
    speed: float
    manual_commanded: bool
    load_version: int
    motion_version: int
    reset_version: int
    action_version: int
    pending_action: str | None
    shutdown: bool


class SimulationManager:
    """Own all MuJoCo state and expose a small UI-safe command API."""

    def __init__(self, initial_robot: str = "panda"):
        self._lock = threading.RLock()
        self._active_robot = self._resolve_robot(initial_robot)
        self._requested_robot: str | None = None
        self._vx = 0.0
        self._wz = 0.0
        self._speed = 0.5
        self._manual_commanded = False
        self._load_version = 0
        self._motion_version = 0
        self._reset_version = 0
        self._action_version = 0
        self._pending_action: str | None = None
        self._shutdown = False

    @property
    def robot_choices(self) -> tuple[str, ...]:
        return tuple(info.label for info in ROBOTS.values())

    @property
    def initial_robot_label(self) -> str:
        with self._lock:
            return ROBOTS[self._active_robot].label

    def actions_for(self, robot: str) -> tuple[str, ...]:
        return ROBOTS[self._resolve_robot(robot)].actions

    def _resolve_robot(self, robot: str) -> str:
        normalized = robot.strip().casefold()
        for key, info in ROBOTS.items():
            if normalized in {key.casefold(), info.label.casefold()}:
                return key
        raise ValueError(f"unknown robot: {robot}")

    def snapshot(self) -> SimulationState:
        with self._lock:
            return SimulationState(
                active_robot=self._active_robot,
                requested_robot=self._requested_robot,
                vx=self._vx,
                wz=self._wz,
                speed=self._speed,
                manual_commanded=self._manual_commanded,
                load_version=self._load_version,
                motion_version=self._motion_version,
                reset_version=self._reset_version,
                action_version=self._action_version,
                pending_action=self._pending_action,
                shutdown=self._shutdown,
            )

    def load_robot(self, robot: str) -> str:
        return self.request_load(robot)

    def request_load(self, robot: str) -> str:
        key = self._resolve_robot(robot)
        with self._lock:
            self._requested_robot = key
            self._vx = 0.0
            self._wz = 0.0
            self._manual_commanded = False
            self._load_version += 1
            self._motion_version += 1
        return f"Loading {ROBOTS[key].label} in MuJoCo…"

    def move(self, vx: float, wz: float) -> str:
        with self._lock:
            self._vx = float(np.clip(vx, -1.0, 1.0))
            self._wz = float(np.clip(wz, -1.0, 1.0))
            self._manual_commanded = True
            self._motion_version += 1
            speed = self._speed
        return f"Moving at {speed:.1f}× · press Stop to hold"

    def stop(self) -> str:
        with self._lock:
            self._vx = 0.0
            self._wz = 0.0
            self._manual_commanded = True
            self._motion_version += 1
        return "Stopped"

    def set_speed(self, speed: float) -> str:
        with self._lock:
            self._speed = float(np.clip(speed, 0.1, 1.0))
            if self._manual_commanded:
                self._motion_version += 1
            value = self._speed
        return f"Speed set to {value:.1f}×"

    def reset(self) -> str:
        with self._lock:
            self._vx = 0.0
            self._wz = 0.0
            self._manual_commanded = False
            self._reset_version += 1
            self._motion_version += 1
            label = ROBOTS[self._active_robot].label
        return f"Resetting {label} to its demo pose…"

    def action(self, name: str) -> str:
        with self._lock:
            robot = self._requested_robot or self._active_robot
            normalized = name.replace("_", " ").strip().casefold()
            canonical = next(
                (
                    action
                    for action in ROBOTS[robot].actions
                    if action.casefold() == normalized
                ),
                None,
            )
            if canonical is None:
                raise ValueError(f"{name!r} is not an action for {ROBOTS[robot].label}")
            self._pending_action = canonical
            self._action_version += 1
        return f"Action: {canonical}"

    def shutdown(self) -> None:
        with self._lock:
            self._shutdown = True

    def _begin_robot(self, selected: str) -> tuple[RobotController, SimulationState]:
        controller = create_controller(selected)
        with self._lock:
            self._active_robot = selected
            self._requested_robot = None
            state = self.snapshot()
        print(f"Loaded {ROBOTS[selected].label}", flush=True)
        return controller, state

    @staticmethod
    def _configure_camera(viewer, controller: RobotController) -> None:
        viewer.cam.lookat[:] = controller.model.stat.center
        viewer.cam.distance = (
            controller.info.camera_distance * controller.model.stat.extent
        )
        viewer.cam.azimuth = controller.info.camera_azimuth
        viewer.cam.elevation = controller.info.camera_elevation

    def run(self) -> int:
        """Own the viewer lifecycle and step physics until the window closes."""
        import mujoco.viewer

        selected = self.snapshot().active_robot
        while not self.snapshot().shutdown:
            requested = self.snapshot().requested_robot
            if requested is not None:
                selected = requested
            controller, initial = self._begin_robot(selected)
            last_load = initial.load_version
            last_motion = initial.motion_version
            last_reset = initial.reset_version
            last_action = initial.action_version
            reload_robot: str | None = None

            with mujoco.viewer.launch_passive(
                controller.model,
                controller.data,
                show_left_ui=True,
                show_right_ui=True,
            ) as viewer:
                self._configure_camera(viewer, controller)
                configure_mujoco_viewer()
                frame_period = 1.0 / 60.0
                physics_steps = max(
                    1, round(frame_period / controller.model.opt.timestep)
                )

                while viewer.is_running():
                    started = time.monotonic()
                    state = self.snapshot()
                    if state.shutdown:
                        return 0
                    if state.load_version != last_load:
                        reload_robot = state.requested_robot or state.active_robot
                        break

                    with viewer.lock():
                        if state.reset_version != last_reset:
                            controller.reset_to_demo()
                            last_reset = state.reset_version
                        if state.action_version != last_action:
                            if state.pending_action is not None:
                                controller.action(state.pending_action)
                            last_action = state.action_version
                        if state.motion_version != last_motion:
                            if state.manual_commanded:
                                controller.set_motion(
                                    state.vx, state.wz, state.speed
                                )
                            last_motion = state.motion_version
                        for _ in range(physics_steps):
                            controller.step()

                    viewer.sync()
                    delay = frame_period - (time.monotonic() - started)
                    if delay > 0:
                        time.sleep(delay)

            if reload_robot is None:
                self.shutdown()
                break
            selected = reload_robot

        return 0
