"""Pass bar for the simulated arena."""

from __future__ import annotations

import mujoco
import numpy as np
import pytest

from smolvla_mbot_push.config import mix
from smolvla_mbot_push.run import build_parser
from smolvla_mbot_push.sim import PushEnv


class TestActionMixing:
    def test_neutral_stops(self):
        assert mix((0.0, 0.0)) == (0.0, 0.0)

    def test_forward_drives_both_wheels_equally(self):
        left, right = mix((1.0, 0.0))
        assert left == right == 1.0

    def test_reverse_is_negative(self):
        assert mix((-1.0, 0.0)) == (-1.0, -1.0)

    def test_pure_steer_counter_rotates(self):
        left, right = mix((0.0, 1.0))
        assert left > 0 > right

    def test_overflow_rescales_instead_of_clipping(self):
        """Hard forward plus hard turn must keep its curvature: if both wheels
        clipped to 1.0 the robot would drive straight instead of turning."""
        left, right = mix((1.0, 1.0))
        assert left != right
        assert max(abs(left), abs(right)) == pytest.approx(1.0)

    def test_out_of_range_input_is_clamped(self):
        assert mix((5.0, 0.0)) == mix((1.0, 0.0))


class TestArena:
    def test_observation_is_an_rgb_frame(self):
        with PushEnv(render_size=128, seed=0) as env:
            frame = env.reset(seed=0)
            assert frame.shape == (128, 128, 3)
            assert frame.dtype == np.uint8

    def test_same_seed_renders_identically(self):
        """Recorded episodes and evaluation runs have to agree frame for frame,
        which is why the camera is static and the renderer is warmed up."""
        frames = []
        for _ in range(2):
            with PushEnv(render_size=128, seed=0) as env:
                frame = env.reset(seed=11)
                for _ in range(5):
                    frame = env.step((0.6, 0.2))
                frames.append(frame)
        assert np.array_equal(frames[0], frames[1])

    def test_different_seeds_give_different_layouts(self):
        with PushEnv(render_size=128, seed=0) as env:
            env.reset(seed=1)
            first = env.body_xy("block").copy()
            env.reset(seed=2)
            assert not np.allclose(first, env.body_xy("block"))

    def test_driving_forward_pushes_the_block_without_climbing_it(self):
        with PushEnv(render_size=128, seed=0) as env:
            env.reset(seed=0)
            env._set_pose(env._chassis_qpos, x=-0.25, y=0.0, z=0.035, yaw=0.0)
            env._set_pose(env._block_qpos, x=-0.05, y=0.0, z=0.030, yaw=0.0)
            mujoco.mj_forward(env.model, env.data)

            start = env.body_xy("block").copy()
            for _ in range(40):
                env.step((1.0, 0.0))

            assert env.body_xy("block")[0] - start[0] > 0.15
            block_id = mujoco.mj_name2id(env.model, mujoco.mjtObj.mjOBJ_BODY, "block")
            # Riding up over the block is the classic flat-pusher failure.
            assert env.data.xpos[block_id][2] < 0.045

    def test_walls_contain_the_robot(self):
        with PushEnv(render_size=128, seed=0) as env:
            env.reset(seed=1)
            for _ in range(120):
                env.step((1.0, 0.25))
            robot = env.body_xy("chassis")
            assert abs(robot[0]) < 0.55 and abs(robot[1]) < 0.45

    def test_zero_action_leaves_the_robot_still(self):
        with PushEnv(render_size=128, seed=0) as env:
            env.reset(seed=3)
            before = env.body_xy("chassis").copy()
            for _ in range(10):
                env.step((0.0, 0.0))
            assert np.allclose(before, env.body_xy("chassis"), atol=2e-3)

    def test_turning_changes_heading(self):
        with PushEnv(render_size=128, seed=0) as env:
            env.reset(seed=4)
            before = env.body_xy("chassis").copy()
            for _ in range(20):
                env.step((0.0, 1.0))
            # Spinning in place: heading changes, position barely moves.
            assert np.linalg.norm(env.body_xy("chassis") - before) < 0.05


class TestCli:
    def test_commands_parse(self):
        parser = build_parser()
        for command in ("check", "drive"):
            assert parser.parse_args([command]).func is not None

    def test_unknown_command_rejected(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["nonsense"])


class TestKeyboardTeleop:
    """The arena has to be drivable with nothing plugged in."""

    def _teleop_with_keys(self, monkeypatch, held):
        import pygame

        from smolvla_mbot_push import ui

        monkeypatch.setattr(pygame.joystick, "get_count", lambda: 0)
        monkeypatch.setattr(pygame, "init", lambda: None)
        monkeypatch.setattr(pygame.joystick, "init", lambda: None)

        teleop = ui.Teleop()
        pressed = {key: True for key in held}
        monkeypatch.setattr(
            pygame.key, "get_pressed", lambda: _Keys(pressed)
        )
        return teleop

    def test_falls_back_to_keyboard_without_a_controller(self, monkeypatch):
        teleop = self._teleop_with_keys(monkeypatch, [])
        assert not teleop.using_gamepad
        assert "keyboard" in teleop.source

    def test_held_key_ramps_up_instead_of_jumping(self, monkeypatch):
        """A square-wave demonstration is poor material to clone, so a held key
        approaches full deflection rather than snapping to it."""
        import pygame

        teleop = self._teleop_with_keys(monkeypatch, [pygame.K_UP])
        first = teleop.read(0.1)[0]
        assert 0.0 < first < 1.0
        second = teleop.read(0.1)[0]
        assert second > first

    def test_held_key_eventually_reaches_full(self, monkeypatch):
        import pygame

        teleop = self._teleop_with_keys(monkeypatch, [pygame.K_UP])
        for _ in range(20):
            action = teleop.read(0.1)
        assert action[0] == pytest.approx(1.0)

    def test_release_returns_to_zero(self, monkeypatch):
        import pygame

        teleop = self._teleop_with_keys(monkeypatch, [pygame.K_UP])
        for _ in range(20):
            teleop.read(0.1)
        monkeypatch.setattr(pygame.key, "get_pressed", lambda: _Keys({}))
        for _ in range(20):
            action = teleop.read(0.1)
        assert action[0] == pytest.approx(0.0)

    def test_wasd_matches_arrows(self, monkeypatch):
        import pygame

        arrows = self._teleop_with_keys(monkeypatch, [pygame.K_LEFT])
        left = arrows.read(0.1)[1]
        wasd = self._teleop_with_keys(monkeypatch, [pygame.K_a])
        assert wasd.read(0.1)[1] == pytest.approx(left)
        assert left < 0.0


class _Keys:
    """Stand-in for pygame's key-state sequence."""

    def __init__(self, pressed: dict):
        self._pressed = pressed

    def __getitem__(self, key: int) -> bool:
        return self._pressed.get(key, False)


class TestDatasetRoundTrip:
    """The recorded dataset is the one artifact that is expensive to redo, so
    its shape is part of the pass bar."""

    def test_records_and_reloads(self, tmp_path):
        from lerobot.datasets.lerobot_dataset import LeRobotDataset

        from smolvla_mbot_push.config import CONTROL_HZ
        from smolvla_mbot_push.record import TASK, _build_features

        size = 64
        root = tmp_path / "ds"
        dataset = LeRobotDataset.create(
            repo_id="local/test",
            fps=int(CONTROL_HZ),
            features=_build_features(size),
            root=str(root),
            robot_type="diffdrive",
        )

        rng = np.random.default_rng(0)
        with PushEnv(render_size=size, seed=0) as env:
            frame = env.reset(seed=0)
            last = np.zeros(2, dtype=np.float32)
            for _ in range(6):
                action = rng.uniform(-1, 1, 2).astype(np.float32)
                dataset.add_frame(
                    {
                        "observation.images.overhead": frame,
                        "observation.state": last,
                        "action": action,
                        "task": TASK,
                    }
                )
                frame = env.step(action)
                last = action
            dataset.save_episode()

        # Skipping finalize() leaves a dataset that looks written but will not
        # reload, and the CLI recorder normally calls it for you.
        dataset.finalize()

        reloaded = LeRobotDataset("local/test", root=str(root))
        assert reloaded.num_episodes == 1
        assert reloaded.num_frames == 6
        assert reloaded[0]["task"] == TASK

    def test_state_is_the_previous_action(self, tmp_path):
        """Temporal alignment: the state fed at step t must be the action
        commanded at t-1, since the real robot has no other proprioception."""
        from lerobot.datasets.lerobot_dataset import LeRobotDataset

        from smolvla_mbot_push.config import CONTROL_HZ
        from smolvla_mbot_push.record import TASK, _build_features

        root = tmp_path / "ds"
        dataset = LeRobotDataset.create(
            repo_id="local/test",
            fps=int(CONTROL_HZ),
            features=_build_features(64),
            root=str(root),
            robot_type="diffdrive",
        )
        actions = [np.array([0.1 * i, -0.1 * i], dtype=np.float32) for i in range(5)]
        with PushEnv(render_size=64, seed=0) as env:
            frame = env.reset(seed=0)
            last = np.zeros(2, dtype=np.float32)
            for action in actions:
                dataset.add_frame(
                    {
                        "observation.images.overhead": frame,
                        "observation.state": last,
                        "action": action,
                        "task": TASK,
                    }
                )
                frame = env.step(action)
                last = action
            dataset.save_episode()
        dataset.finalize()

        reloaded = LeRobotDataset("local/test", root=str(root))
        for i in range(1, 5):
            assert np.allclose(reloaded[i]["observation.state"], reloaded[i - 1]["action"], atol=1e-5)


class TestInteractivePlacement:
    """Scene setting by hand is how the real rig will be used, so the geometry
    and the teleport semantics are part of the pass bar."""

    def test_pixel_world_round_trip(self):
        with PushEnv(render_size=256, seed=0) as env:
            env.reset(seed=0)
            for point in [(0.0, 0.0), (0.35, 0.0), (-0.4, 0.3), (0.2, -0.25)]:
                pixel = env.world_to_pixel(*point)
                assert np.allclose(env.pixel_to_world(*pixel), point, atol=1e-6)

    def test_centre_of_image_is_under_the_camera(self):
        with PushEnv(render_size=256, seed=0) as env:
            env.reset(seed=0)
            centre = env.pixel_to_world(127.5, 127.5)
            assert np.allclose(centre, [0.0, 0.0], atol=1e-6)

    def test_image_y_axis_is_flipped_relative_to_world(self):
        """Rows increase downwards while the camera's y axis points up; getting
        this backwards would make dragging feel inverted."""
        with PushEnv(render_size=256, seed=0) as env:
            env.reset(seed=0)
            top = env.pixel_to_world(128, 20)
            bottom = env.pixel_to_world(128, 236)
            assert top[1] > bottom[1]

    def test_place_block_moves_it(self):
        with PushEnv(render_size=64, seed=0) as env:
            env.reset(seed=0)
            env.place_block(0.30, 0.10)
            assert np.allclose(env.body_xy("block"), [0.30, 0.10], atol=1e-3)

    def test_place_robot_keeps_heading_when_yaw_omitted(self):
        with PushEnv(render_size=64, seed=0) as env:
            env.reset(seed=0)
            yaw = env.robot_yaw()
            env.place_robot(-0.30, 0.15)
            assert env.robot_yaw() == pytest.approx(yaw, abs=1e-6)
            assert np.allclose(env.body_xy("chassis"), [-0.30, 0.15], atol=1e-3)

    def test_place_robot_sets_yaw_when_given(self):
        with PushEnv(render_size=64, seed=0) as env:
            env.reset(seed=0)
            env.place_robot(0.0, 0.0, yaw=1.0)
            assert env.robot_yaw() == pytest.approx(1.0, abs=1e-6)

    def test_teleport_clears_momentum(self):
        """Without zeroing velocity a moving body keeps its momentum through a
        teleport and shoots off the moment the policy resumes."""
        with PushEnv(render_size=64, seed=0) as env:
            env.reset(seed=0)
            for _ in range(10):
                env.step((1.0, 0.0))
            env.place_robot(0.0, 0.0, yaw=0.0)
            settled = env.body_xy("chassis").copy()
            env.settle(0.2)
            assert np.allclose(env.body_xy("chassis"), settled, atol=5e-3)
