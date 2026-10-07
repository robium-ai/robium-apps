"""Durable checks for the Gradio-to-MuJoCo application boundary."""

from __future__ import annotations

from multiprocessing import Pipe
import threading

import numpy as np
import pytest

from robot_zoo.app import build_parser
from robot_zoo.bridge import SimulationProxy, serve_commands
from robot_zoo.controllers import (
    ROBOTS,
    Go2Controller,
    PandaController,
    TurtleBotController,
    create_controller,
)
from robot_zoo.desktop import (CONTROLLER_WIDTH, CONTROLLER_HEIGHT, ControllerWindow, controller_window, save_controller_window)
from robot_zoo.gradio_ui import build_control_ui
from robot_zoo.simulation import SimulationManager


def test_cli_accepts_every_robot() -> None:
    parser = build_parser()
    for robot in ROBOTS:
        args = parser.parse_args(["run", "--robot", robot])
        assert callable(args.func)


def test_controller_window_floats_and_remembers_geometry(tmp_path) -> None:
    state_path = tmp_path / "window.json"
    frame = controller_window(state_path)
    assert frame.width == CONTROLLER_WIDTH == 560
    assert frame.height == CONTROLLER_HEIGHT == 440
    assert frame.width > frame.height
    moved = ControllerWindow(frame.x, frame.y, 820, 600)
    save_controller_window(moved, state_path)
    restored = controller_window(state_path)
    assert restored.width == 820 and restored.height == 600
    state_path.write_text('{"width": -1, "height": "bad", "x": -99999}')
    restored = controller_window(state_path)
    assert restored.width >= 560 and restored.height >= 440
    if restored.x is not None:
        assert restored.x >= 0


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
    assert manager.action("low_profile") == "Action: Low profile"
    assert manager.snapshot().pending_action == "Low profile"


def test_gradio_ui_contains_core_controls() -> None:
    demo = build_control_ui(SimulationManager("panda"))
    config = demo.get_config_file()
    labels = {
        component.get("props", {}).get("value")
        for component in config["components"]
    }
    assert {"Load", "Reset robot"} <= labels
    pilot = next(c for c in config["components"] if c.get("props", {}).get("elem_id") == "joystick-panel")
    assert 'data-stick="move"' in pilot["props"]["html_template"]
    assert 'data-stick="turn"' in pilot["props"]["html_template"]
    assert "teleop" in pilot["props"]["server_fns"]
    assert any(
        isinstance(value, str) and "double-click a body to select" in value
        for value in labels
    )


def test_models_have_expected_controller_shape() -> None:
    panda = create_controller("panda")
    turtlebot = create_controller("turtlebot3")
    go2 = create_controller("go2")

    assert isinstance(panda, PandaController) and panda.model.nu == 8
    assert isinstance(turtlebot, TurtleBotController) and turtlebot.model.nu == 2
    assert isinstance(go2, Go2Controller) and go2.model.nu == 12


def test_panda_velocity_command_moves_cartesian_target_within_bounds() -> None:
    panda = create_controller("panda")
    before = panda.target.copy()
    panda.set_motion(vx=1.0, wz=0.0, speed=1.0)
    for _ in range(100):
        panda.step()
    assert panda.target[0] > before[0]
    assert panda.target[0] <= 0.72


@pytest.mark.parametrize("vx,wz,sign", [(1,0,1),(-1,0,-1),(0,1,1),(0,-1,-1)])
def test_turtlebot_drives_turns_and_stops(vx,wz,sign) -> None:
    bot = create_controller("turtlebot3")
    dt = bot.model.opt.timestep
    for _ in range(round(1 / dt)):
        bot.step()
    start = bot.data.qpos[:2].copy()
    bot.set_motion(vx=vx, wz=wz, speed=1)
    for _ in range(round(3 / dt)):
        bot.step()
        assert np.isfinite(bot.data.qpos).all()
        assert bot.data.xmat[1, 8] > .95
        assert np.all(np.abs(bot.data.ctrl) <= 6.67)
    travel = bot.data.qpos[:2] - start
    yaw = np.arctan2(bot.data.xmat[1, 3], bot.data.xmat[1, 0])
    if vx:
        assert sign * travel[0] > .25
        assert abs(travel[1]) < .05
    else:
        assert sign * yaw > 1.0
        assert np.linalg.norm(travel) < .08
    bot.stop()
    for _ in range(round(1 / dt)):
        bot.step()
    assert np.linalg.norm(bot.data.qvel[:6]) < .02
    bot.reset_to_demo()
    assert np.allclose(bot.data.qpos[:2], 0)
    bot.step()
    assert np.allclose(bot.data.ctrl, 0)


def test_robot_specific_actions_change_controller_targets() -> None:
    panda = create_controller("panda")
    start_height = float(panda.target[2])
    assert panda.action("Raise")
    assert panda.target[2] > start_height

    go2 = create_controller("go2")
    assert go2.action("Low profile")
    assert go2._pending_profile == "Low profile"


def test_go2_posture_controller_stays_upright() -> None:
    go2 = create_controller("go2")
    for _ in range(round(3.0 / go2.model.opt.timestep)):
        go2.step()
    assert go2.data.qpos[2] > 0.20
    assert abs(go2.data.qpos[3]) > 0.90
    assert np.isfinite(go2.data.ctrl).all()


def test_joystick_bridge_and_lease_expiry(monkeypatch):
    now = [10.0]
    monkeypatch.setattr("robot_zoo.simulation.time.monotonic", lambda: now[0])
    ui, sim = Pipe()
    manager = SimulationManager("go2")
    thread = threading.Thread(target=serve_commands, args=(manager, sim), daemon=True)
    thread.start()
    proxy = SimulationProxy(ui, "go2")
    proxy.teleop("go2", .8, -.5, .3)
    state = manager.snapshot()
    assert (state.vx, state.vy, state.wz) == (.8, -.5, .3)
    now[0] += .51
    state = manager.snapshot()
    assert (state.vx, state.vy, state.wz) == (0., 0., 0.)
    proxy.teleop("go2", 1, 1, 1, "Low profile")
    state = manager.snapshot()
    assert (state.vx, state.vy, state.wz) == (0., 0., 0.)
    assert state.pending_action == "Low profile"
    proxy.shutdown()
    thread.join(timeout=1)


def test_joystick_rejects_invalid_and_wrong_robot_frames():
    manager = SimulationManager("go2")
    manager.teleop("go2", 1, 1, 1)
    with pytest.raises(ValueError):
        manager.teleop("go2", float("nan"), 0, 0)
    assert manager.snapshot().vx == 0
    manager.load_robot("panda")
    manager.teleop("go2", 1, 1, 1)
    assert manager.snapshot().vx == manager.snapshot().vy == 0
    assert manager.snapshot().pending_action is None


@pytest.mark.parametrize("vx,vy,wz,axis,sign", [
    (1,0,0,0,1), (-1,0,0,0,-1), (0,1,0,1,1), (0,-1,0,1,-1),
    (0,0,1,2,1), (0,0,-1,2,-1),
])
def test_go2_policy_tracks_six_directions_and_stops(vx,vy,wz,axis,sign):
    go2 = create_controller("go2")
    go2.set_motion(vx, wz, 1, vy=vy)
    for i in range(2000):  # Four seconds at the pinned 500 Hz physics rate.
        go2.step()
        if i > 250:
            assert go2.data.qpos[2] > .24
            assert go2.data.xmat[1,8] > .9
    if axis < 2:
        assert go2.data.qpos[axis] * sign > .5
    else:
        w,x,y,z = go2.data.qpos[3:7]
        yaw = np.arctan2(2*(w*z+x*y),1-2*(y*y+z*z))
        assert yaw * sign > 1.0
    go2.stop()
    velocities = []
    for i in range(1250):
        go2.step()
        if i > 1000:
            velocities.append(np.linalg.norm(go2.data.qvel[:3]))
    assert np.mean(velocities) < .06
    assert go2.data.xmat[1,8] > .95


def test_go2_profiles_transition_from_walking_and_resume():
    go2 = create_controller("go2")
    go2.set_motion(1,0,1)
    for _ in range(1500): go2.step()
    heights = {}
    for name in ["Low profile", "High profile", "Stand"]:
        assert go2.action(name)
        for _ in range(1600): go2.step()
        heights[name] = go2.data.qpos[2]
        assert go2.data.xmat[1,8] > .95
        assert np.isfinite(go2.data.ctrl).all()
    assert .15 < heights["Low profile"] < .23
    assert heights["High profile"] > heights["Low profile"] + .08
    go2.action("Low profile")
    for _ in range(1600): go2.step()
    before = go2.data.qpos[1]
    go2.set_motion(0,0,1,vy=1)
    for _ in range(2000): go2.step()
    assert go2.data.qpos[1] > before + .5
    assert go2.data.xmat[1,8] > .95
    go2.reset_to_demo()
    assert not go2.policy.network.history.count_nonzero()
