import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("offline_training", Path(__file__).parents[1] / "training/pipeline.py")
pipeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline)


def episode(root, name="demo", *, invalid=False):
    path = root / name
    path.mkdir()
    meta = {"result": "saved", "camera_only": False, "frames": 2,
            "throttle_power_percent": 75, "steering_power_percent": 25,
            "started_monotonic": 100, "ended_monotonic": 101}
    (path / "episode.json").write_text(json.dumps(meta))
    rows = []
    for i in range(2):
        rows.append({"kind": "frame", "action": [.5, -.2], "action_valid": not invalid,
                     "estimated_capture_t": 100 + i / 10,
                     "joystick": {"t": 100 + i / 10 - .005, "controller_connected": True, "record_held": True},
                     "width": 320, "height": 240, "jpeg_quality": 85, "target_fps": 10,
                     "sequence": i, "stream_generation": 0, "recording_segment": 0})
    (path / "events.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    return path


def test_split_is_deterministic_disjoint_whole_episodes():
    episodes = [{"id": str(i), "frames": [i] * 10} for i in range(16)]
    splits = pipeline.split_episodes(episodes)
    assert splits == pipeline.split_episodes(episodes)
    assert len(splits["train"]) == 13 and len(splits["val"]) == 3
    assert not {e["id"] for e in splits["train"]} & {e["id"] for e in splits["val"]}
    assert sum(len(s) for s in splits.values()) == len(episodes)


def test_export_excludes_button_tests_and_rejects_bad_pairing(tmp_path):
    for i in range(4):
        episode(tmp_path, f"demo-{i}")
    episode(tmp_path, next(iter(pipeline.TEST_CLIPS)))
    assert len(pipeline.raw_episodes(tmp_path)) == 4
    episode(tmp_path, "invalid", invalid=True)
    with pytest.raises(ValueError, match="Invalid paired action"):
        pipeline.raw_episodes(tmp_path)


def test_export_rejects_future_input_and_splits_gaps_without_losing_frames(tmp_path):
    for i in range(4):
        episode(tmp_path, f"demo-{i}")
    log = tmp_path / "demo-0/events.jsonl"
    rows = [json.loads(line) for line in log.read_text().splitlines()]
    rows[0]["joystick"]["t"] = 100.01
    log.write_text("\n".join(json.dumps(r) for r in rows))
    with pytest.raises(ValueError, match="Future joystick"):
        pipeline.raw_episodes(tmp_path)
    rows[0]["joystick"]["t"] = 99.99
    rows[1]["sequence"] = 2
    log.write_text("\n".join(json.dumps(r) for r in rows))
    exported = pipeline.raw_episodes(tmp_path)
    assert exported[0]["segments"] == [(0, 1), (1, 2)]
    assert len(exported[0]["frames"]) == 2


def test_cost_guard_limits_allocation_and_refuses_unknown_price():
    smoke = pipeline.cost_guard(1.8, 900, 10)
    main = pipeline.cost_guard(1.8, 14400, 10 - smoke)
    assert smoke + main == pytest.approx(7.65)
    with pytest.raises(ValueError, match="exceeds remaining budget"):
        pipeline.cost_guard(1.8, 14400, 6)
    with pytest.raises(ValueError):
        pipeline.cost_guard(float("nan"), 900, 10)


def test_retry_requires_confirmed_failure_and_blocks_uncertain_or_live_allocation():
    ledger = {"jobs": [{"id": "original", "stage": "smoke"}]}
    for status in ("SCHEDULING", "RUNNING", "COMPLETED"):
        with pytest.raises(ValueError, match="already submitted"):
            pipeline.check_stage_retry(ledger, "smoke", {"original": status})
    for status in ("CANCELED", "ERROR"):
        pipeline.check_stage_retry(ledger, "smoke", {"original": status})
    ledger["jobs"].append({"id": None, "stage": "smoke"})
    with pytest.raises(ValueError, match="already submitted"):
        pipeline.check_stage_retry(ledger, "smoke", {"original": "CANCELED"})


def test_explicit_selection_supports_three_clips_and_enforces_manual_pose(tmp_path):
    paths = [episode(tmp_path, f'guards-{i}') for i in range(3)]
    for path in paths:
        log = path / 'events.jsonl'
        rows = [json.loads(line) for line in log.read_text().splitlines()]
        for row in rows:
            row['joystick'].update(control_mode='manual', source='gamepad', head_action=[0, 20/85])
        log.write_text('\n'.join(json.dumps(r) for r in rows))
    args = {'selected': paths, 'min_episodes': 3, 'tilt_deg': 20}
    assert len(pipeline.raw_episodes(tmp_path, **args)) == 3
    with pytest.raises(ValueError, match='Camera tilt'):
        pipeline.raw_episodes(tmp_path, selected=paths, min_episodes=3, tilt_deg=0)
    rows[0]['joystick']['control_mode'] = 'model'
    (paths[-1] / 'events.jsonl').write_text('\n'.join(json.dumps(r) for r in rows))
    with pytest.raises(ValueError, match='Model-generated'):
        pipeline.raw_episodes(tmp_path, **args)


def test_inference_capture_is_rejected_even_if_moved_or_explicitly_selected(tmp_path):
    path = episode(tmp_path)
    meta_path = path / 'episode.json'
    meta = json.loads(meta_path.read_text())
    meta['training_eligible'] = False
    meta_path.write_text(json.dumps(meta))
    with pytest.raises(ValueError, match='Inference-only recording'):
        pipeline.raw_episodes(tmp_path)
    with pytest.raises(ValueError, match='Inference-only recording'):
        pipeline.raw_episodes(tmp_path, selected=[path], min_episodes=1)


def test_mixed_pose_selection_validates_each_source_and_requires_complete_mapping(tmp_path):
    paths = [episode(tmp_path, name) for name in ('old', 'new')]
    tilts = {'old': 0, 'new': 20}
    for path in paths:
        log = path / 'events.jsonl'
        rows = [json.loads(line) for line in log.read_text().splitlines()]
        for row in rows:
            row['joystick']['head_action'] = [0, tilts[path.name] / 85]
        log.write_text('\n'.join(json.dumps(r) for r in rows))
    args = {'selected': paths, 'min_episodes': 2, 'tilt_deg': 20}
    assert len(pipeline.raw_episodes(tmp_path, **args, episode_tilts_deg=tilts)) == 2
    with pytest.raises(ValueError, match='match every selected clip'):
        pipeline.raw_episodes(tmp_path, **args, episode_tilts_deg={'new': 20})
    with pytest.raises(ValueError, match='Camera tilt'):
        pipeline.raw_episodes(tmp_path, **args, episode_tilts_deg={'old': 20, 'new': 20})
    rows[0]['joystick'].pop('head_action')
    (paths[-1] / 'events.jsonl').write_text('\n'.join(json.dumps(r) for r in rows))
    with pytest.raises(ValueError, match='Camera tilt'):
        pipeline.raw_episodes(tmp_path, **args, episode_tilts_deg=tilts)
