"""Durable checks for the Gradio-to-MuJoCo application boundary."""

from __future__ import annotations

from multiprocessing import Pipe
import threading

import numpy as np

from robot_zoo.app import build_parser
from robot_zoo.bridge import SimulationProxy, serve_commands
from robot_zoo.controllers import (
    ROBOTS,
    Go2Controller,
    PandaController,
    StretchController,
    create_controller,
)
from robot_zoo.desktop import CONTROLLER_WIDTH, WINDOW_GAP, controller_window
from robot_zoo.gradio_ui import build_control_ui
from robot_zoo.simulation import SimulationManager


def test_cli_accepts_every_robot() -> None:
    parser = build_parser()
    for robot in ROBOTS:
        args = parser.parse_args(["run", "--robot", robot])
        assert callable(args.func)


def test_controller_window_is_slim_and_has_a_gap() -> None:
    frame = controller_window()
    assert frame.width == CONTROLLER_WIDTH == 390
    assert frame.height >= 620
    assert WINDOW_GAP > 0


def test_process_bridge_exposes_manager_commands() -> None:
    ui_connection, simulation_connection = Pipe(duplex=True)
    manager = SimulationManager("panda")
    thread = threading.Thread(
        target=serve_commands,
        args=(manager, simulation_connection),
        daemon=True,
    )
    thread.start()
    proxy = SimulationProxy(ui_connection, "panda")

    assert proxy.initial_robot_label == "Franka Panda"
    assert proxy.set_speed(0.7) == "Speed set to 0.7×"
    assert proxy.move(1.0, 0.0).startswith("Moving at 0.7×")
    assert manager.snapshot().vx == 1.0
    proxy.shutdown()
    thread.join(timeout=1)
    assert manager.snapshot().shutdown


def test_manager_registry_and_actions_cover_every_robot() -> None:
    manager = SimulationManager("panda")
    assert manager.robot_choices == tuple(info.label for info in ROBOTS.values())
    for key, info in ROBOTS.items():
        assert manager.actions_for(key) == info.actions
        assert manager.actions_for(info.label) == info.actions


def test_manager_commands_are_state_only() -> None:
    manager = SimulationManager("panda")
    manager.set_speed(0.8)
    manager.move(vx=0.5, wz=-0.25)
    moving = manager.snapshot()
    assert moving.vx == 0.5
    assert moving.wz == -0.25
    assert moving.speed == 0.8
    assert moving.manual_commanded

    manager.stop()
    stopped = manager.snapshot()
    assert stopped.vx == stopped.wz == 0.0

    manager.load_robot("Unitree Go2")
    loading = manager.snapshot()
    assert loading.requested_robot == "go2"
    assert not loading.manual_commanded
    assert manager.action("sit") == "Action: Sit"
    assert manager.snapshot().pending_action == "Sit"


def test_gradio_ui_contains_core_controls() -> None:
    demo = build_control_ui(SimulationManager("panda"))
    config = demo.get_config_file()
    labels = {
        component.get("props", {}).get("value")
        for component in config["components"]
    }
    assert {"Load", "↑", "↓", "←", "→", "Stop", "Reset robot"} <= labels
    assert any(
        isinstance(value, str) and "double-click a body to select" in value
        for value in labels
    )


def test_models_have_expected_controller_shape() -> None:
    panda = create_controller("panda")
    stretch = create_controller("stretch")
    go2 = create_controller("go2")

    assert isinstance(panda, PandaController) and panda.model.nu == 8
    assert isinstance(stretch, StretchController) and stretch.model.nu == 10
    assert isinstance(go2, Go2Controller) and go2.model.nu == 12


def test_panda_velocity_command_moves_cartesian_target_within_bounds() -> None:
    panda = create_controller("panda")
    before = panda.target.copy()
    panda.set_motion(vx=1.0, wz=0.0, speed=1.0)
    for _ in range(100):
        panda.step()
    assert panda.target[0] > before[0]
    assert panda.target[0] <= 0.72


def test_stretch_velocity_command_stops() -> None:
    stretch = create_controller("stretch")
    stretch.set_motion(vx=1.0, wz=0.0, speed=0.6)
    stretch.step()
    assert np.linalg.norm(stretch.data.ctrl[:2]) > 0

    stretch.stop()
    stretch.step()
    assert np.allclose(stretch.data.ctrl[:2], 0)


def test_robot_specific_actions_change_controller_targets() -> None:
    panda = create_controller("panda")
    start_height = float(panda.target[2])
    assert panda.action("Raise")
    assert panda.target[2] > start_height

    stretch = create_controller("stretch")
    assert stretch.action("Extend")
    assert stretch.data.ctrl[3] > 0

    go2 = create_controller("go2")
    assert go2.action("Sit")
    assert go2.crouch > 0.3


def test_go2_posture_controller_stays_upright() -> None:
    go2 = create_controller("go2")
    for _ in range(round(3.0 / go2.model.opt.timestep)):
        go2.step()
    assert go2.data.qpos[2] > 0.20
    assert abs(go2.data.qpos[3]) > 0.90
    assert np.isfinite(go2.data.ctrl).all()
