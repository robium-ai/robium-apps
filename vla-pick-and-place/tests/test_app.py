"""The regression bar for this app. Deliberately small.

Only failures that have actually happened here, or that would ship something
false, get a test. Everything else was cut — a suite you avoid running is
worse than no suite.

Six fast tests, no network, ~3 s. The gateway smoke lives in test_demo.py
and is `slow`.
"""

import tomllib
from pathlib import Path

import numpy as np
import pytest

from vla_pick_and_place import config
from vla_pick_and_place.data import datasets
from vla_pick_and_place.demo import dashboard, ui
from vla_pick_and_place.env import contract
from vla_pick_and_place.env.contract import ACTION_LOW
from vla_pick_and_place.env.nexus import NexusPickAndPlace
from vla_pick_and_place.policy import controllers

APP_ROOT = Path(__file__).resolve().parents[1]


def test_pins_are_exact_and_agree_with_config():
    """The app owns no physics and no data, so the pins ARE the contract."""
    deps = tomllib.loads((APP_ROOT / "pyproject.toml").read_text())["project"]["dependencies"]
    assert f"so101-nexus=={config.NEXUS_VERSION}" in deps

    import so101_nexus

    assert so101_nexus.__version__ == config.NEXUS_VERSION
    for pin in datasets.REGISTRY.values():
        assert len(pin.revision) == 40, f"{pin.repo_id} must pin a commit sha, not a branch"


def test_the_live_environment_still_matches_the_recorded_contract():
    """One test for the whole schema: spaces, observation keys, camera shape,
    control rate, info keys, success key. A so101-nexus bump that moves any of
    them fails here instead of silently relabelling what the page shows."""
    with NexusPickAndPlace() as env:
        assert contract.diff(contract.capture(env)) == []

        # A dead GL backend renders a black frame rather than raising, so the
        # pixels are the assertion.
        obs, _ = env.reset(seed=0)
        for cam in (config.OBS_WRIST, config.OBS_OVERHEAD):
            assert obs[cam].mean() > 20, f"{cam} is nearly black"
            assert obs[cam].std() > 5, f"{cam} is a flat fill"


def test_the_arm_can_be_driven_from_another_thread():
    """The failure this guards is a HANG, not an exception: MuJoCo's GL context
    is thread-affine, and Gradio runs every request on an arbitrary worker. It
    also checks the commanded target is what actually reaches the simulator."""
    import threading

    from vla_pick_and_place.demo.session import SimWorker

    worker = SimWorker().start()
    try:
        reset = worker.reset(seed=0)
        target = np.array(reset.state, dtype=np.float32)
        target[3] = float(
            np.clip(target[3] - 0.6, worker.action_low[3], worker.action_high[3])
        )

        result: dict = {}

        def body():
            try:
                result["frames"] = list(worker.drive(target, n_steps=30))
            except BaseException as exc:  # noqa: BLE001
                result["error"] = exc

        t = threading.Thread(target=body)
        t.start()
        t.join(timeout=120)
        assert not t.is_alive(), "driving from another thread deadlocked"
        assert "error" not in result, result.get("error")

        frames = result["frames"]
        assert np.allclose(frames[-1].action, target, atol=1e-5), "action was rewritten"
        assert abs(frames[-1].state[3] - target[3]) < abs(reset.state[3] - target[3]), (
            "wrist_flex did not track the commanded target"
        )
    finally:
        worker.close()


def test_no_controller_is_available_and_each_says_why():
    """The honest state of this milestone. When an ACT checkpoint finally
    matches this environment, this is the test that must be updated on
    purpose — which is the point of it existing."""
    assert controllers.available() == []
    for c in controllers.REGISTRY.values():
        assert len(c.unavailable_reason) > 40, f"{c.key} is unavailable with no explanation"
    # The old 0%-success checkpoint must not survive anywhere in config.
    text = Path(config.__file__).read_text()
    for stale in ("train_2026-07-15", "smolvla", "robium-admin"):
        assert stale not in text, f"config.py still references {stale!r}"


def test_the_page_says_which_source_it_is_showing():
    """A viewer cannot tell live simulation from recorded playback by looking,
    so the label is the only thing keeping the page honest."""
    from types import SimpleNamespace

    def frame(**kw):
        base = dict(
            source="simulator", step=3, total=1024,
            state=np.zeros(6, np.float32), action=np.zeros(6, np.float32),
            reward=0.25, success=False, info={}, units="radians",
        )
        base.update(kw)
        return SimpleNamespace(**base)

    assert "source <b>simulator</b>" in ui._readout(frame())
    assert "units radians" in ui._readout(frame())

    played = ui._readout(frame(source="dataset:johnsutor/x#0", units="lerobot rows"))
    assert "dataset:johnsutor/x#0" in played and "lerobot rows" in played
    assert "polic" not in played.lower()

    assert "SUCCESS" not in ui._readout(frame(success=False))
    assert "SUCCESS" in ui._readout(frame(success=True))


@pytest.mark.parametrize("selector", [".rd-split", ".rd-viewer", ".rd-cams", ".rd-rail"])
def test_no_workspace_container_may_wrap(selector):
    """Gradio's row/column classes carry `flex-wrap: wrap`, which silently
    moves whole panels off screen at full size — they render, report visible,
    and are nowhere anyone can see them. This hid the control rail once."""
    css = dashboard.css()
    assert any(
        selector in block and "nowrap" in block for block in css.split("}")
    ), f"{selector} does not force flex-wrap: nowrap"


def test_reset_state_is_clamped_into_the_slider_range():
    """Reset noise can park a joint marginally outside the actuator range, and
    Gradio rejects an out-of-range value outright rather than clamping."""
    just_outside = np.array(ACTION_LOW, dtype=np.float64) - 1e-4
    for v, low, high in zip(ui._slider_values(just_outside), ui.SLIDER_LOW, ui.SLIDER_HIGH):
        assert low <= v <= high


@pytest.mark.slow
def test_the_pinned_demonstrations_match_this_environment():
    """The finding that chose the dataset: both published sets pass a schema
    check, and only one was recorded in this scene. Also asserts the recorded
    units really are the dataset's (degrees), not the simulator's radians."""
    with NexusPickAndPlace() as env:
        obs, _ = env.reset(seed=0)
        reference = {
            config.OBS_WRIST: obs[config.OBS_WRIST],
            config.OBS_OVERHEAD: obs[config.OBS_OVERHEAD],
        }

    ok = datasets.verify(datasets.PRIMARY, reference_frames=reference)
    assert ok.problems == [], "\n".join(ok.problems)

    bad = datasets.verify(datasets.ALTERNATE, reference_frames=reference)
    assert not bad.ok and any("camera identity" in p for p in bad.problems)

    player = datasets.EpisodePlayer(datasets.PRIMARY, episode=0)
    first, last = player.frame(0), player.frame(len(player) - 1)
    assert last[config.OBS_OVERHEAD].mean() > 20
    assert not np.allclose(first[config.OBS_STATE], last[config.OBS_STATE])
    assert last["success"] == pytest.approx(1.0)
    assert np.abs(last["action"]).max() > 10.0, "recorded rows should be degrees"


@pytest.mark.slow
def test_expert_records_data_this_environment_can_execute():
    """The whole point of collecting our own data, in one test.

    The expert drives in TCP space (upstream solves the IK) but records the
    JOINT targets the environment derived. If that contract holds, replaying a
    recorded episode's actions through the demo's own `pd_joint_pos` env
    reproduces the success — which is what makes this data trainable for a
    controller the demo can actually run.
    """
    import tempfile

    from vla_pick_and_place.config import LOCAL_DATASET_REPO_ID
    from vla_pick_and_place.data.record import record
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    with tempfile.TemporaryDirectory() as tmp:
        # LeRobotDataset.create insists on making the root itself.
        root = Path(tmp) / "ds"
        summary = record(n_episodes=1, root=root, progress=lambda _m: None)
        assert summary["episodes"] == 1
        assert summary["fps"] == 50, "fps must be the real control rate, not a playback rate"

        ds = LeRobotDataset(LOCAL_DATASET_REPO_ID, root=root, episodes=[0])
        assert ds.num_frames > 50
        actions = np.stack([np.asarray(ds[i]["action"]) for i in range(ds.num_frames)])

        # Radians, not LeRobot degrees: the whole vector stays inside the
        # actuator range, which a degree-valued recording never would.
        assert np.abs(actions).max() <= 2.75

        with NexusPickAndPlace(control_mode="pd_joint_pos") as env:
            info = env.reset(seed=int(summary["seeds"].split("..")[0]))[1]
            for action in actions:
                _obs, _r, term, trunc, info = env.step(action)
                if term or trunc:
                    break
        assert info["success"], (
            "recorded joint actions did not reproduce the episode in pd_joint_pos; "
            "the dataset is not executable by this app's action contract"
        )
