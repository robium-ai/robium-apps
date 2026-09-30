"""Inference-only recordings: camera video plus decisions, never expert data."""
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor

from .core import Episode
from .policy import bounded_action

_EXPORTS = ThreadPoolExecutor(max_workers=1, thread_name_prefix='inference-video')


def export_video(path):
    """Encode off the control thread; retain JPEGs and logs even on failure."""
    status = path / 'video-status.json'
    status.write_text(json.dumps({'phase': 'encoding'}))
    try:
        rows = [json.loads(line) for line in (path / 'events.jsonl').read_text().splitlines()]
        frames = [r for r in rows if r['kind'] == 'frame']
        if not frames:
            status.write_text(json.dumps({'phase': 'empty', 'frames': 0}))
            return
        lines = ['ffconcat version 1.0']
        for i, frame in enumerate(frames):
            following = frames[i + 1]['estimated_capture_t'] if i + 1 < len(frames) else frame['estimated_capture_t'] + .1
            lines.extend([f"file '{frame['image']}'",
                          f"duration {max(.001, following - frame['estimated_capture_t']):.6f}"])
        lines.append(f"file '{frames[-1]['image']}'")
        (path / 'video.ffconcat').write_text('\n'.join(lines) + '\n')
        with (path / 'video-export.log').open('w') as log:
            subprocess.run(['ffmpeg', '-nostdin', '-y', '-loglevel', 'error', '-f', 'concat',
                            '-safe', '1', '-i', 'video.ffconcat', '-an', '-c:v', 'libx264',
                            '-preset', 'veryfast', '-crf', '18', '-pix_fmt', 'yuv420p',
                            '-movflags', '+faststart', '-fps_mode', 'vfr', 'video.mp4'],
                           cwd=path, stdout=log, stderr=log, check=True, timeout=300)
        status.write_text(json.dumps({'phase': 'complete', 'frames': len(frames), 'video': 'video.mp4'}))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        status.write_text(json.dumps({'phase': 'error', 'error': str(error)}))


class InferenceEpisode(Episode):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.meta.update(training_eligible=False, capture_purpose='inference-review',
                         recording_control='R toggles inference video and decisions',
                         video_file='video.mp4', decisions_file='events.jsonl')
        self.write_meta()
        self.last_decision = None
        self.export_future = None

    def record_decision(self, prediction, *, mode, selected_action, manual_action,
                        available, held, sampled_at):
        identity = ((prediction or {}).get('stream_generation'),
                    (prediction or {}).get('sequence'), mode, tuple(selected_action), available, held)
        if identity == self.last_decision:
            return
        self.last_decision = identity
        self.add({'kind': 'policy_decision', 't': sampled_at, 'prediction': prediction,
                  'bounded_prediction': bounded_action(prediction['raw_action']) if prediction else None,
                  'mode': mode, 'model_held': held, 'drive_available': available,
                  'manual_action': list(manual_action),
                  'selected_action': list(selected_action) if available else [0.0, 0.0]})

    def close(self, result, *, ended_at=None):
        path = super().close(result, ended_at=ended_at)
        self.export_future = _EXPORTS.submit(export_video, path)
        return path
