import time

import pytest

from lego_stackchan_drive.core import Controls, Workers
from lego_stackchan_drive.metrics import CameraMetrics, quality_report


def frame(t, seq, generation=0):
    return {
        'kind': 'frame', 't': t, 'sensor_us': int(t * 1e6),
        'device_sent_us': int(t * 1e6), 'sequence': seq,
        'stream_generation': generation, 'width': 320, 'height': 240,
        'jpeg_quality': 75, 'target_fps': 8,
    }


@pytest.mark.parametrize('source', ['LEGO Bluetooth', 'Camera pan/tilt'])
def test_actuator_failure_does_not_stop_camera(monkeypatch, source):
    controls = Controls()
    controls.update((1, 0), True)
    worker = Workers(controls, 'unused', 'unused')
    worker.fail(RuntimeError('disconnected'), source)
    assert not worker.stop.is_set() and not controls.drive_available

    def stream(*_args):
        yield frame(time.monotonic(), 1)
        worker.stop.set()

    monkeypatch.setattr('lego_stackchan_drive.core.frames', stream)
    worker.camera()
    assert worker.latest['sequence'] == 1 and worker.camera_error is None


def test_camera_recovers_after_more_than_three_outages(monkeypatch):
    worker = Workers(Controls(), 'unused', 'unused')
    attempts = []
    monkeypatch.setattr(worker.stop, 'wait', lambda _duration: False)

    def stream(*_args):
        attempts.append(1)
        if len(attempts) <= 4:
            raise TimeoutError('offline')
        yield frame(time.monotonic(), 1)
        worker.stop.set()

    monkeypatch.setattr('lego_stackchan_drive.core.frames', stream)
    worker.camera()
    assert len(attempts) == 5 and worker.latest is not None
    assert worker.camera_error is None and worker.camera_metrics.snapshot()['reconnects'] == 4


def test_metrics_show_missing_sequences_and_stale_rate():
    metrics = CameraMetrics()
    metrics.add(frame(1, 1))
    metrics.add(frame(1.125, 3))
    snapshot = metrics.snapshot(1.125)
    assert snapshot['received_fps'] == snapshot['capture_fps'] == 8
    assert snapshot['sequence_missing'] == 1
    assert metrics.snapshot(2)['received_fps'] == 0
    metrics.reconnect()
    metrics.add(frame(2.1, 1, generation=1))
    snapshot = metrics.snapshot(2.1)
    assert snapshot['sequence_missing'] == 1  # Reset is not wraparound or negative loss.
    assert snapshot['gaps_over_250ms'] == snapshot['reconnects'] == 1


def test_quality_flags_gap_even_if_average_fps_is_high():
    rows = [frame(1 + i * .1, i) for i in range(100)]
    for row in rows[50:]:
        row['t'] += .5
    report = quality_report(rows, rows)
    assert report['camera_fps'] > 8
    assert not report['timing_check_passed']
    assert 'frame gap exceeds twice the target period' in report['timing_issues']
    assert report['sensor_drops'] is None


def test_constant_eight_fps_passes_provisional_quality_check():
    rows = [frame(1 + i * .125, i) for i in range(81)]
    assert quality_report(rows, rows)['timing_check_passed']


def test_camera_timing_does_not_override_operator_recording_label(tmp_path):
    import json

    from lego_stackchan_drive.core import Episode

    episode = Episode(tmp_path, 'test camera', 25, camera_only=True)
    episode.close('success')
    metadata = json.loads((episode.path / 'episode.json').read_text())
    assert metadata['result'] == 'success'
    assert 'camera_quality' not in metadata


def test_sensor_timing_excludes_clock_reset_between_connections():
    metrics = CameraMetrics()
    metrics.add(frame(100, 10))
    row = frame(100.125, 0, generation=1)
    row['sensor_us'] = 1000
    metrics.add(row)
    assert metrics.snapshot(100.125)['capture_fps'] == 0
    assert metrics.snapshot(100.125)['sequence_missing'] == 0


def test_queue_overflow_invalidates_recording_without_killing_preview():
    import queue

    worker = Workers(Controls(), 'unused', 'unused')
    worker.events = queue.Queue(maxsize=1)
    worker.emit({'kind': 'frame'})
    worker.emit({'kind': 'frame'})
    assert 'overflow' in worker.error
    assert not worker.stop.is_set() and not worker.controls.drive_available


def test_profile_change_is_flagged_even_with_perfect_timing():
    rows = [frame(1 + i * .125, i) for i in range(81)]
    rows[30]['jpeg_quality'] = 50
    report = quality_report(rows, rows)
    assert not report['timing_check_passed']
    assert 'fixed camera profile unverified or changed' in report['timing_issues']


def test_benchmark_evaluates_the_requested_compression_and_fps():
    rows = [frame(1 + i / 6, i) for i in range(61)]
    for row in rows:
        row['target_fps'], row['jpeg_quality'] = 6, 55
    profile = {'target_fps': 6, 'jpeg_quality': 55, 'width': 320, 'height': 240, 'max_gap_s': 2 / 6}
    report = quality_report(rows, rows, profile)
    assert report['camera_profile_verified'] and report['timing_check_passed']
    assert not quality_report(rows, rows)['camera_profile_verified']


def test_recording_inspection_uses_actual_ten_fps_profile(tmp_path):
    import io
    import json

    import pygame

    from lego_stackchan_drive.core import Episode, inspect_episode

    image = io.BytesIO()
    surface = pygame.Surface((320, 240))
    surface.fill((30, 60, 90))
    pygame.image.save(surface, image, 'frame.jpg')
    episode = Episode(tmp_path, 'ten FPS camera', 25, camera_only=True)
    for i in range(61):
        row = frame(episode.start + 1 + i / 10, i)
        row.update(target_fps=10, jpeg_quality=85, jpeg=image.getvalue(),
                   estimated_capture_t=row['t'])
        episode.add(row)
    path = episode.close('success')
    metadata = json.loads((path / 'episode.json').read_text())
    assert metadata['camera_profile']['max_gap_s'] == .2
    report = inspect_episode(path)
    assert report['result'] == 'success'
    assert report['camera_profile_verified'] and report['timing_check_passed']
