"""Observed stream health; stream sequence gaps are not sensor drop counts."""

import math
import threading
import time
from collections import deque
from itertools import pairwise

CAMERA_PROFILE = {
    "width": 320, "height": 240, "jpeg_quality": 75,
    "target_fps": 8, "max_gap_s": 0.25,
    "timing": "Fixed source target recorded per frame; received timing measured independently",
    "sensor_drop_count": "unknown: firmware sequences encoded stream frames only",
}


def percentile(values, fraction):
    values = sorted(values)
    return values[min(len(values) - 1, math.ceil(len(values) * fraction) - 1)] if values else None


class DriveMetrics:
    """Recent write rate and required Bluetooth transport ACK latency."""

    def __init__(self):
        self.lock = threading.Lock()
        self.recent = deque(maxlen=128)

    def add(self, event):
        with self.lock:
            self.recent.append((event['send_started'], event['t']))

    def snapshot(self, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            rows = [row for row in self.recent if row[1] >= now - 5]
        return {
            'hz': (len(rows) - 1) / (rows[-1][0] - rows[0][0]) if len(rows) > 1 else 0,
            'reply_p95_ms': percentile([(end - start) * 1000 for start, end in rows], .95),
        }


class CameraMetrics:
    def __init__(self):
        self.lock = threading.Lock()
        self.recent = deque(maxlen=256)
        self.total = self.missing = self.gaps = self.reconnects = self.stale = 0
        self.last = None
        self.device = {}
        self.max_gap = 0.0

    def reconnect(self):
        with self.lock:
            self.reconnects += 1

    def add(self, event):
        with self.lock:
            if self.last:
                gap = event['t'] - self.last['t']
                self.max_gap = max(self.max_gap, gap)
                self.gaps += gap > CAMERA_PROFILE['max_gap_s']
                if event['stream_generation'] == self.last['stream_generation']:
                    self.missing += max(0, event['sequence'] - self.last['sequence'] - 1)
            self.device = {key: event.get(key) for key in (
                'encode_us', 'capture_wait_us', 'previous_send_us', 'missed_slots',
                'width', 'height', 'jpeg_quality', 'target_fps', 'firmware', 'network_mode',
            )}
            self.total += 1
            self.stale += bool(event.get('stale', False))
            # Keep only timing fields: never retain JPEGs in the metrics window.
            self.last = {key: event[key] for key in ('t', 'sensor_us', 'sequence', 'stream_generation')}
            self.recent.append(self.last)

    def snapshot(self, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            rows = [r for r in self.recent if r['t'] >= now - 5]
            age = now - self.last['t'] if self.last else None
            intervals = [b['t'] - a['t'] for a, b in pairwise(rows)]
            sensor_intervals = [
                (b['sensor_us'] - a['sensor_us']) / 1e6 for a, b in pairwise(rows)
                if a['stream_generation'] == b['stream_generation'] and b['sensor_us'] > a['sensor_us']
            ]
            live = age is not None and age <= 0.5
            return {
                **self.device,
                'received_fps': (len(rows) - 1) / (now - rows[0]['t'])
                if live and len(rows) > 1 and now > rows[0]['t'] else 0.0,
                'capture_fps': len(sensor_intervals) / sum(sensor_intervals)
                if live and sensor_intervals else 0.0,
                'age_s': age, 'gap_p95_s': percentile(intervals, .95),
                'max_gap_s': self.max_gap, 'frames': self.total,
                'sequence_missing': self.missing, 'gaps_over_250ms': self.gaps,
                'reconnects': self.reconnects, 'stale_frames': self.stale,
            }


def quality_report(frames, rows, profile=None):
    profile = CAMERA_PROFILE if profile is None else profile
    # Intentional recording pauses create independent contiguous segments.
    # Do not count their omitted images/time as camera loss or timing jitter.
    pairs = [(a, b) for a, b in pairwise(frames)
             if a.get('recording_segment', 0) == b.get('recording_segment', 0)]
    intervals = [b['t'] - a['t'] for a, b in pairs]
    duration = sum(intervals)
    fps = len(intervals) / duration if duration else None
    capture_intervals = [
        (b['sensor_us'] - a['sensor_us']) / 1e6 for a, b in pairs
        if a.get('stream_generation', 0) == b.get('stream_generation', 0)
        and b['sensor_us'] > a['sensor_us']
    ]
    missing = sum(
        max(0, b['sequence'] - a['sequence'] - 1) for a, b in pairs
        if a.get('stream_generation', 0) == b.get('stream_generation', 0)
    )
    reconnects = sum(r['kind'] == 'camera_gap' for r in rows)
    stale = sum(bool(r.get('stale')) for r in frames)
    reasons = []
    if len(frames) < 2 or duration < 5:
        reasons.append('at least five seconds of frames required to assess cadence')
    if fps is not None and not profile['target_fps'] * .95 <= fps <= profile['target_fps'] * 1.05:
        reasons.append('average FPS outside target +/- 5%')
    if any(dt > profile['max_gap_s'] for dt in intervals):
        reasons.append('frame gap exceeds twice the target period')
    jitter = percentile([abs(dt - 1 / profile['target_fps']) for dt in intervals], .95)
    if jitter is not None and jitter > .05:
        reasons.append('p95 interval deviation exceeds 50 ms from the target period')
    if missing:
        reasons.append('missing stream sequences')
    if reconnects:
        reasons.append('stream interruptions')
    missed_slots = 0
    for a, b in pairs:
        if a.get('stream_generation', 0) == b.get('stream_generation', 0):
            missed_slots += max(0, b.get('missed_slots', 0) - a.get('missed_slots', 0))
    if missed_slots:
        reasons.append('device missed scheduled frame slots')
    verified = bool(frames) and all(
        all(r.get(key) == profile[key] for key in ('width', 'height', 'jpeg_quality', 'target_fps'))
        for r in frames
    )
    if not verified:
        reasons.append('fixed camera profile unverified or changed')
    if stale:
        reasons.append('stale frames')
    return {
        'camera_fps': fps,
        'captured_frames_fps': len(capture_intervals) / sum(capture_intervals) if capture_intervals else None,
        'p95_capture_gap_s': percentile(capture_intervals, .95), 'max_camera_gap_s': max(intervals, default=None),
        'p95_camera_gap_s': percentile(intervals, .95), 'p95_interval_deviation_s': jitter,
        'sequence_missing': missing, 'camera_interruptions': reconnects,
        'stale_frames': stale, 'sensor_drops': None, 'device_missed_slots': missed_slots,
        'camera_profile_verified': verified,
        'encode_p95_ms': percentile([r['encode_us'] / 1000 for r in frames if 'encode_us' in r], .95),
        'send_p95_ms': percentile([r['previous_send_us'] / 1000 for r in frames if 'previous_send_us' in r], .95),
        'timing_check_passed': not reasons, 'timing_issues': reasons,
    }
