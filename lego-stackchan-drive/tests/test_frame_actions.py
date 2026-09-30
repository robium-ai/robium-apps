import io
import json

import pygame

from lego_stackchan_drive.core import Controls, Episode, Workers, inspect_episode


def sample(control, at, action, available=True):
    control.camera_tick(at)
    control.update(action, available)
    control.refresh_action(action, sampled_at=at, sample={
        'source': 'gamepad', 'controller': 'test controller', 'controller_connected': True,
        'joystick_action': list(action), 'requested_action': list(action),
        'head_action': [0, 0], 'focused': True, 'stop_pressed': False,
    })


def test_frame_uses_latest_sample_before_capture_not_receipt():
    controls = Controls()
    sample(controls, 10, (.2, 0))
    sample(controls, 10.1, (.8, 0))
    worker = Workers(controls, 'unused', 'unused')
    frame = {'estimated_capture_t': 10.05, 't': 10.15}
    worker.attach_frame_action(frame)
    assert frame['action'] == [.2, 0]
    assert frame['joystick']['t'] == 10 and frame['action_valid']


def test_multiple_images_reuse_input_with_its_original_timestamp():
    controls = Controls()
    sample(controls, 10, (.5, -.2))
    worker = Workers(controls, 'unused', 'unused')
    for capture_t in (10.01, 10.11, 10.21):
        frame = {'estimated_capture_t': capture_t}
        worker.attach_frame_action(frame)
        assert frame['action'] == [.5, -.2]
        assert frame['joystick']['t'] == 10


def test_missing_or_expired_input_is_explicit_not_fabricated():
    controls = Controls()
    worker = Workers(controls, 'unused', 'unused')
    frame = {'estimated_capture_t': 10}
    worker.attach_frame_action(frame)
    assert frame['action'] is None and frame['joystick'] is None
    sample(controls, 10, (.5, 0))
    frame = {'estimated_capture_t': 10.3}
    worker.attach_frame_action(frame)
    assert frame['action'] is None and not frame['action_valid']
    assert frame['joystick']['requested_action'] == [.5, 0]


def test_requested_input_is_distinct_from_unavailable_action_and_ble_write():
    controls = Controls()
    sample(controls, 10, (1, 0), available=False)
    worker = Workers(controls, 'unused', 'unused')
    for start, complete, action in ((9.9, 9.95, [.2, 0]), (10.01, 10.08, [.8, 0])):
        worker.emit({'kind': 'command', 'send_started': start, 't': complete,
                     'action': action, 'wheels': [5, 5], 'transport_ack': True,
                     'hub_consumed': False})
    frame = {'estimated_capture_t': 10.05}
    worker.attach_frame_action(frame)
    assert frame['joystick']['requested_action'] == [1, 0]
    assert frame['action'] == [0, 0]
    assert frame['last_ble_command']['action'] == [.2, 0]
    assert frame['last_ble_command']['t'] == 9.95


def test_every_saved_image_retains_action_and_operator_label(tmp_path):
    controls = Controls()
    worker = Workers(controls, 'unused', 'unused')
    episode = Episode(tmp_path, 'paired images', 25, camera_only=True)
    surface = pygame.Surface((320, 240))
    surface.fill((40, 80, 120))
    jpeg = io.BytesIO()
    pygame.image.save(surface, jpeg, 'frame.jpg')
    for i in range(21):
        capture_t = episode.start + 1 + i / 10
        sample(controls, capture_t - .01, (i / 20, 0))
        frame = {
            'kind': 'frame', 't': capture_t + .08, 'estimated_capture_t': capture_t,
            'sequence': i, 'stream_generation': 0, 'sensor_us': int(capture_t * 1e6),
            'device_sent_us': int((capture_t + .07) * 1e6), 'jpeg': jpeg.getvalue(),
            'target_fps': 10, 'jpeg_quality': 85, 'width': 320, 'height': 240,
        }
        worker.attach_frame_action(frame)
        episode.add(frame)
    path = episode.close('success')
    rows = [json.loads(line) for line in (path / 'events.jsonl').read_text().splitlines()]
    assert len(rows) == 21
    assert [row['action'] for row in rows] == [[i / 20, 0] for i in range(21)]
    assert all((path / row['image']).exists() for row in rows)
    report = inspect_episode(path)
    assert report['frames'] == report['image_action_samples'] == 21
    assert report['images_without_action_sample'] == 0 and report['result'] == 'success'
