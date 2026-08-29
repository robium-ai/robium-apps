import importlib

import pytest

from go2_locomotion import config


def test_smoke_train_uses_unified_headless_workflow():
    cmd = config.train_cmd("smoke")
    assert cmd[:4] == [config.ISAACLAB_LAUNCHER, "train", "--rl_library", config.RL_LIBRARY]
    assert cmd[cmd.index("--task") + 1] == config.TASK
    assert cmd[cmd.index("--num_envs") + 1] == str(config.SMOKE.num_envs)
    assert cmd[cmd.index("--max_iterations") + 1] == str(config.SMOKE.max_iterations)
    assert cmd[cmd.index("--viz") + 1] == "none"


def test_full_profile_allows_installed_task_default():
    cmd = config.train_cmd("full")
    if config.FULL.num_envs is None:
        assert "--num_envs" not in cmd
    if config.FULL.max_iterations is None:
        assert "--max_iterations" not in cmd


def test_play_selects_checkpoint_and_video():
    cmd = config.play_cmd("/runs/model_300.pt", video=True)
    assert cmd[cmd.index("--checkpoint") + 1] == "/runs/model_300.pt"
    assert "--video" in cmd
    assert "--enable_cameras" in cmd


def test_list_envs_uses_installed_launcher():
    assert config.list_envs_cmd() == [
        config.ISAACLAB_LAUNCHER,
        "-p",
        config.LIST_ENVS_SCRIPT,
    ]


def test_legacy_style_remains_an_explicit_compatibility_option(monkeypatch):
    monkeypatch.setenv("ISAACLAB_CLI_STYLE", "legacy")
    legacy = importlib.reload(config)
    try:
        cmd = legacy.train_cmd("smoke")
        assert cmd[:3] == [legacy.ISAACLAB_LAUNCHER, "-p", legacy.LEGACY_TRAIN_SCRIPT]
        assert "--headless" in cmd
    finally:
        monkeypatch.setenv("ISAACLAB_CLI_STYLE", "unified")
        importlib.reload(config)


def test_unknown_cli_style_fails_loudly(monkeypatch):
    monkeypatch.setattr(config, "CLI_STYLE", "mystery")
    with pytest.raises(ValueError, match="unified.*legacy"):
        config.train_cmd("smoke")
