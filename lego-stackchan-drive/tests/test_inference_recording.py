import json
import queue
import shutil
import subprocess
from types import SimpleNamespace

import pygame
import pytest

from lego_stackchan_drive.main import inference_recording


def test_r_toggle_saves_video_and_decisions_without_controller(tmp_path):
    if not shutil.which('ffmpeg'):
        pytest.skip('ffmpeg required for MP4 export')
    source = tmp_path / 'source.jpg'
    image = pygame.Surface((320, 240))
    image.fill((240, 240, 240))
    pygame.draw.line(image, (0, 0, 0), (160, 240), (240, 0), 15)
    pygame.image.save(image, str(source))
    jpeg = source.read_bytes()
    args = SimpleNamespace(root=tmp_path / 'captures', task='inference review', power=25,
                           camera_only=False, policy=tmp_path / 'checkpoint')
    workers = SimpleNamespace(events=queue.Queue())
    episode, _ = inference_recording(None, args, workers, pressed=True,
                                      can_start=True, sampled_at=100)
    assert not episode.meta['training_eligible']
    prediction = {'raw_action': [1.1, -.2], 'sequence': 1, 'stream_generation': 0,
                  'capture_t': 100.1, 'inference_ms': 20}
    episode.record_decision(prediction, mode='model', selected_action=(1, -.2),
                            manual_action=(0, 0), available=True, held=True, sampled_at=100.2)
    episode.record_decision(prediction, mode='manual', selected_action=(0, 0),
                            manual_action=(0, 0), available=True, held=False, sampled_at=100.25)
    original = episode
    episode, _ = inference_recording(episode, args, workers, pressed=False,
                                      can_start=False, sampled_at=100.3)
    assert episode is original  # Neither key release nor link loss toggles R off.
    for i, t in enumerate([99.9, 100.1, 100.2, 100.4, 101]):
        workers.events.put({'kind': 'frame', 't': t+.02, 'estimated_capture_t': t,
                            'sequence': i, 'jpeg': jpeg})
    episode, _ = inference_recording(episode, args, workers, pressed=True,
                                      can_start=False, sampled_at=101)
    assert episode is None
    original.export_future.result(timeout=15)
    meta = json.loads((original.path / 'episode.json').read_text())
    assert meta['frames'] == 3 and meta['result'] == 'saved'
    assert meta['policy_checkpoint'] == str(args.policy.resolve())
    assert not meta['training_eligible']
    rows = [json.loads(s) for s in (original.path/'events.jsonl').read_text().splitlines()]
    decisions = [r for r in rows if r['kind'] == 'policy_decision']
    assert decisions[0]['prediction']['raw_action'] == [1.1, -.2]
    assert decisions[0]['bounded_prediction'] == [1, -.2]
    assert decisions[1]['selected_action'] == [0, 0]
    assert json.loads((original.path/'video-status.json').read_text())['phase'] == 'complete'
    result = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                             '-show_entries', 'stream=width,height', '-of', 'json',
                             str(original.path/'video.mp4')], capture_output=True, text=True, check=True)
    assert json.loads(result.stdout)['streams'][0] == {'width': 320, 'height': 240}
