"""Mac-testable guards on the single-source command builders (config.py).

This is the ONE part of go2-locomotion that runs without a GPU: config.py's
command construction is pure Python. These tests catch config/command drift
before it ever reaches the pod. They assert against config CONSTANTS, never
re-typed literals — the vla-trial lesson (a test hardcoding "--steps=2000" went
silently stale when the constant changed; see that app's battle scar #10).
"""

from go2_locomotion import config


def test_smoke_train_is_headless_and_capped():
    cmd = config.train_cmd(full=False)
    assert "--headless" in cmd
    assert "--task" in cmd and config.TASK in cmd
    # Smoke overrides the iteration count down to the tiny SMOKE value.
    assert "--max_iterations" in cmd
    i = cmd.index("--max_iterations")
    assert cmd[i + 1] == str(config.SMOKE_MAX_ITERATIONS)
    # Smoke uses the smoke env count.
    n = cmd.index("--num_envs")
    assert cmd[n + 1] == str(config.SMOKE_NUM_ENVS)


def test_full_train_uses_task_default_iterations():
    cmd = config.train_cmd(full=True)
    # FULL must NOT override --max_iterations (uses the task's own default).
    assert "--max_iterations" not in cmd
    n = cmd.index("--num_envs")
    assert cmd[n + 1] == str(config.FULL_NUM_ENVS)


def test_smoke_and_full_differ_in_num_envs():
    # Assert against the constants, not literals, so this can't go stale.
    assert config.SMOKE_NUM_ENVS != config.FULL_NUM_ENVS
    smoke_n = config.train_cmd(full=False)[config.train_cmd(full=False).index("--num_envs") + 1]
    full_n = config.train_cmd(full=True)[config.train_cmd(full=True).index("--num_envs") + 1]
    assert smoke_n != full_n


def test_video_requires_enable_cameras():
    # Off-screen video capture in Isaac Lab needs --enable_cameras alongside
    # --video (skill + handoff). If one is present the other must be.
    cmd = config.train_cmd(full=False, video=True)
    assert "--video" in cmd
    assert "--enable_cameras" in cmd


def test_seed_is_pinned_and_shared():
    for cmd in (config.train_cmd(full=False), config.train_cmd(full=True)):
        assert "--seed" in cmd
        assert cmd[cmd.index("--seed") + 1] == str(config.SEED)


def test_play_targets_the_same_task():
    cmd = config.play_cmd()
    assert "--task" in cmd and config.TASK in cmd
