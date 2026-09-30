import io
import json

import pygame
import pytest

from lego_stackchan_drive.core import Episode, inspect_episode
from lego_stackchan_drive.metrics import quality_report


@pytest.fixture
def clock(monkeypatch):
    now = [100.0]
    monkeypatch.setattr('lego_stackchan_drive.core.time.monotonic', lambda: now[0])
    return now


def image_event(t, sequence):
    image = pygame.Surface((320, 240))
    image.fill((20, 70, 90))
    jpeg = io.BytesIO()
    pygame.image.save(image, jpeg, 'frame.jpg')
    return {
        'kind': 'frame', 't': t + .04, 'estimated_capture_t': t,
        'sensor_us': round(t * 1e6), 'device_sent_us': round((t + .02) * 1e6),
        'sequence': sequence, 'stream_generation': 0, 'jpeg': jpeg.getvalue(),
        'width': 320, 'height': 240, 'jpeg_quality': 85, 'target_fps': 10,
        'action': [.5, 0], 'action_valid': True,
        'joystick': {'source': 'gamepad', 'controller_connected': True, 'age_s': .005},
    }


def test_pause_excludes_images_and_commands_and_resume_excludes_late_paused_capture(tmp_path, clock):
    episode = Episode(tmp_path, 'pause test', 25, camera_only=True)
    episode.add(image_event(100.1, 1))
    clock[0] = 101
    assert episode.toggle_pause()
    episode.add(image_event(101.5, 15))
    episode.add({'kind': 'command', 't': 101.5, 'wheels': [75, 75]})
    assert episode.frames == 1 and episode.commands == 0
    clock[0] = 103
    assert not episode.toggle_pause()
    # This JPEG arrives after resume but was captured during the pause.
    delayed = image_event(102, 20)
    delayed['t'] = 103.3
    episode.add(delayed)
    episode.add(image_event(103.2, 32))
    episode.add({'kind': 'command', 't': 103.3, 'wheels': [20, 20]})
    clock[0] = 104
    path = episode.close('success')
    rows = [json.loads(line) for line in (path / 'events.jsonl').read_text().splitlines()]
    frames = [r for r in rows if r['kind'] == 'frame']
    assert [r['sequence'] for r in frames] == [1, 32]
    assert [r['recording_segment'] for r in frames] == [0, 1]
    assert [r['image'] for r in frames] == ['frames/000000.jpg', 'frames/000001.jpg']
    assert len(list((path / 'frames').glob('*.jpg'))) == 2
    assert [r['paused'] for r in rows if r['kind'] == 'recording_state'] == [True, False]
    assert episode.commands == 1
    report = inspect_episode(path)
    assert report['recording_pause_count'] == 1 and report['recording_segments'] == 2
    assert report['sequence_missing'] == 0 and report['image_action_samples'] == 2
    assert episode.meta['recorded_duration_s'] == 2
    assert episode.meta['result'] == 'success'


def test_save_while_paused_keeps_only_active_duration_and_original_label(tmp_path, clock):
    episode = Episode(tmp_path, 'save paused', 25, camera_only=True)
    episode.add(image_event(100.1, 1))
    clock[0] = 102
    episode.toggle_pause()
    clock[0] = 110
    episode.close('rejected')
    assert episode.meta['recorded_duration_s'] == 2
    assert episode.meta['closed_while_paused']
    assert episode.meta['result'] == 'rejected'
    assert episode.meta['frames'] == 1


def test_camera_timing_ignores_intentional_pause_but_detects_loss_within_segment():
    frames = []
    for segment, start in ((0, 100), (1, 120)):
        for i in range(61):
            row = image_event(start + i / 10, segment * 200 + i)
            row['recording_segment'] = segment
            frames.append(row)
    profile = {'width': 320, 'height': 240, 'jpeg_quality': 85, 'target_fps': 10, 'max_gap_s': .2}
    report = quality_report(frames, frames, profile)
    assert report['timing_check_passed'] and report['sequence_missing'] == 0
    assert report['camera_fps'] == pytest.approx(10)
    del frames[30]
    report = quality_report(frames, frames, profile)
    assert not report['timing_check_passed'] and report['sequence_missing'] == 1
