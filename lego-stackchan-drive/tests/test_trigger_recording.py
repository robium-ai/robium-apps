import json
import queue
from types import SimpleNamespace

from lego_stackchan_drive.main import hold_recording
from lego_stackchan_drive.vendor.gamepad import GamepadReading


def frame(t, sequence):
    return {'kind': 'frame', 't': t + .05, 'estimated_capture_t': t,
            'jpeg': b'test-jpeg', 'sequence': sequence, 'action_valid': True}


def test_hold_handoff_release_filters_capture_boundaries_and_saves(tmp_path):
    args = SimpleNamespace(root=tmp_path, task='road', power=25, camera_only=True)
    workers = SimpleNamespace(events=queue.Queue())
    episode, _ = hold_recording(None, args, workers, held=False, can_start=True, sampled_at=100)
    assert episode is None and not list(tmp_path.iterdir())
    episode, _ = hold_recording(None, args, workers, held=True, can_start=False, sampled_at=100)
    assert episode is None
    episode, _ = hold_recording(None, args, workers, held=True, can_start=True, sampled_at=100)
    original = episode
    episode.add(frame(99.9, 0))
    for reading in (GamepadReading(l2=1), GamepadReading(l2=1, r2=1), GamepadReading(r2=1)):
        episode, message = hold_recording(episode, args, workers, held=reading.record_held,
                                          can_start=True, sampled_at=100.5)
        assert episode is original and message is None
    workers.events.put(frame(100.7, 1))
    workers.events.put(frame(101, 2))
    workers.events.put(frame(101.1, 3))
    episode, message = hold_recording(episode, args, workers, held=False,
                                      can_start=True, sampled_at=101)
    assert episode is None and message.startswith('Saved:')
    assert original.frames == 1 and original.meta['result'] == 'saved'
    assert original.meta['recorded_duration_s'] == 1
    rows = [json.loads(line) for line in (original.path / 'events.jsonl').read_text().splitlines()]
    assert [r['sequence'] for r in rows] == [1]
    next_episode, _ = hold_recording(None, args, workers, held=True,
                                     can_start=True, sampled_at=102)
    assert next_episode.path != original.path
    next_episode.close('saved', ended_at=103)


def test_release_or_disconnect_while_paused_saves_same_clip(tmp_path):
    args = SimpleNamespace(root=tmp_path, task='road', power=25, camera_only=True)
    workers = SimpleNamespace(events=queue.Queue())
    episode, _ = hold_recording(None, args, workers, held=True, can_start=True, sampled_at=100)
    episode.add(frame(100.1, 1))
    episode.toggle_pause(101)
    workers.events.put(frame(101.5, 2))
    original = episode
    episode, _ = hold_recording(episode, args, workers, held=GamepadReading().record_held,
                                can_start=False, sampled_at=102)
    assert episode is None
    assert original.meta['result'] == 'saved' and original.frames == 1
    assert original.meta['recorded_duration_s'] == 1
    assert original.meta['recording_pause_count'] == 1
    assert original.meta['closed_while_paused']
