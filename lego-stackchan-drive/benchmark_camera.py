"""Explicit camera collection benchmark; never changes training-recording labels."""

import argparse
import io
import json
import logging
import queue
import statistics
import time
import urllib.request
from itertools import pairwise
from pathlib import Path
from urllib.parse import urlsplit

import pygame

from lego_stackchan_drive.core import Controls, Workers
from lego_stackchan_drive.metrics import percentile, quality_report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seconds', type=float, default=300)
    parser.add_argument('--name', default='8fps-q75-baseline')
    parser.add_argument('--fps', type=int, choices=range(2, 11))
    parser.add_argument('--quality', type=int, choices=range(35, 86))
    parser.add_argument('--throughput', action='store_true', help='Three explicit 4 MiB bulk Wi-Fi transfers')
    args = parser.parse_args()
    if args.seconds < 20:
        parser.error('Use at least 20 seconds')
    logging.basicConfig(level=logging.WARNING, format='%(asctime)s %(message)s')
    config = json.loads(Path('.local/camera.json').read_text())
    if args.throughput:
        ready_deadline = time.monotonic() + 30
        while True:
            request = urllib.request.Request(
                f"http://{urlsplit(config['url']).hostname}:81/camera",
                headers={'X-Stream-Key': config['key']},
            )
            try:
                with urllib.request.urlopen(request, timeout=3) as response:
                    device_status = json.load(response)
                if device_status.get('wifi_connected'):
                    break
            except OSError:
                pass
            if time.monotonic() >= ready_deadline:
                raise RuntimeError('Camera network did not become ready for throughput testing')
            time.sleep(.5)
        trials = []
        for _ in range(3):
            request = urllib.request.Request(
                f"http://{urlsplit(config['url']).hostname}/throughput",
                headers={'X-Stream-Key': config['key']},
            )
            trial_start, received = time.monotonic(), 0
            error = None
            try:
                with urllib.request.urlopen(request, timeout=3) as response:
                    while chunk := response.read(65536):
                        received += len(chunk)
                        if time.monotonic() - trial_start > 30:
                            raise TimeoutError('Bulk transfer exceeded 30 seconds')
                if received != 4 * 1024 * 1024:
                    raise RuntimeError('Incomplete 4 MiB transfer')
            except (OSError, RuntimeError) as failure:
                error = str(failure)
            elapsed = time.monotonic() - trial_start
            trials.append({'bytes': received, 'seconds': elapsed, 'mbps': received * 8 / elapsed / 1e6, 'error': error})
            print(json.dumps(trials[-1]), flush=True)
            time.sleep(.5)
        root = Path('.local/benchmarks') / (time.strftime('%Y%m%d-%H%M%S') + '-bulk-wifi')
        root.mkdir(parents=True)
        (root / 'report.json').write_text(json.dumps({'device_status': device_status, 'trials': trials}, indent=2) + '\n')
        return
    if (args.fps is None) != (args.quality is None):
        parser.error('Supply both --fps and --quality')
    profile_status = None
    if args.fps is not None:
        request = urllib.request.Request(
            f"http://{urlsplit(config['url']).hostname}:81/camera",
            data=json.dumps({'fps': args.fps, 'quality': args.quality}).encode(),
            headers={'X-Stream-Key': config['key'], 'Content-Type': 'application/json'},
        )
        ready_deadline = time.monotonic() + 30
        while True:
            try:
                with urllib.request.urlopen(request, timeout=3) as response:
                    profile_status = json.load(response)
                break
            except OSError:
                if time.monotonic() >= ready_deadline:
                    raise
                time.sleep(.5)
        if (profile_status.get('fps'), profile_status.get('quality')) != (args.fps, args.quality):
            raise RuntimeError('Device did not apply the requested profile')
        time.sleep(.5)  # Let the in-flight encoder frame finish with the previous profile.
    root = Path('.local/benchmarks') / (time.strftime('%Y%m%d-%H%M%S') + '-' + args.name)
    (root / 'frames').mkdir(parents=True)
    workers = Workers(Controls(), config['url'], config['key'], video_only=True)
    rows, sizes = [], []
    started = time.monotonic()
    deadline = started + args.seconds
    next_update = started + 30
    workers.start()
    try:
        with (root / 'events.jsonl').open('w') as output:
            while time.monotonic() < deadline:
                try:
                    event = workers.events.get(timeout=.1)
                except queue.Empty:
                    continue
                row = dict(event)
                if row['kind'] == 'frame':
                    jpeg = row.pop('jpeg')
                    image = f'frames/{len(sizes):06d}.jpg'
                    (root / image).write_bytes(jpeg)
                    row['image'], row['jpeg_bytes'] = image, len(jpeg)
                    # Verify real images, not just transport framing.
                    decoded = pygame.image.load(io.BytesIO(jpeg))
                    if decoded.get_size() != (320, 240):
                        raise RuntimeError('Unexpected frame dimensions')
                    sizes.append(len(jpeg))
                rows.append(row)
                output.write(json.dumps(row) + '\n')
                if time.monotonic() >= next_update:
                    elapsed = time.monotonic() - started
                    stats = workers.camera_metrics.snapshot()
                    print(json.dumps({
                        'elapsed_s': round(elapsed), 'frames': len(sizes),
                        'effective_fps': round(len(sizes) / elapsed, 3),
                        'missing': stats['sequence_missing'], 'retries': stats['reconnects'],
                        'stale': stats['stale_frames'],
                    }), flush=True)
                    next_update += 30
    finally:
        workers.close()
    frame_rows = [r for r in rows if r['kind'] == 'frame']
    if not frame_rows:
        raise RuntimeError('No camera images received')
    target = frame_rows[0].get('target_fps', 8)
    expected = {
        'width': 320, 'height': 240,
        'target_fps': args.fps or target,
        'jpeg_quality': args.quality or frame_rows[0].get('jpeg_quality', 75),
        'max_gap_s': 2 / (args.fps or target),
    }
    measured = quality_report(frame_rows, rows, expected)
    windows = [
        sum(started + i <= r['t'] < started + i + 10 for r in frame_rows) / 10
        for i in range(0, int(args.seconds) - 9, 10)
    ]
    capture_gaps = [
        (b['sensor_us'] - a['sensor_us']) / 1e6
        for a, b in pairwise(frame_rows)
        if a['stream_generation'] == b['stream_generation']
    ]
    reasons = []
    if len(frame_rows) / args.seconds < target * .95:
        reasons.append('effective collection FPS below 95% of target')
    if min(windows, default=0) < target * .9:
        reasons.append('a ten-second window delivered below 90% of target')
    for key in ('sequence_missing', 'camera_interruptions', 'stale_frames', 'device_missed_slots'):
        if measured[key]:
            reasons.append(key)
    if max(capture_gaps, default=0) > 2.1 / target:
        reasons.append('capture interval exceeds two target periods')
    if measured['max_camera_gap_s'] and measured['max_camera_gap_s'] > .5:
        reasons.append('delivery pause exceeds 500 ms')
    if workers.error:
        reasons.append(workers.error)
    if not measured['camera_profile_verified']:
        reasons.append('camera profile changed during test')
    final_status = None
    if frame_rows[0].get('firmware') != '0.4.1':
        try:
            request = urllib.request.Request(
                f"http://{urlsplit(config['url']).hostname}:81/camera",
                headers={'X-Stream-Key': config['key']},
            )
            with urllib.request.urlopen(request, timeout=3) as response:
                final_status = json.load(response)
        except OSError:
            final_status = {'error': 'Device status unavailable after trial'}
    report = {
        'path': str(root), 'duration_s': args.seconds, 'frames': len(sizes),
        'profile': {k: frame_rows[0].get(k) for k in ('firmware', 'width', 'height', 'target_fps', 'jpeg_quality')},
        'effective_collection_fps': len(sizes) / args.seconds,
        'minimum_ten_second_fps': min(windows),
        'ten_second_fps': windows,
        'jpeg_mean_bytes': statistics.mean(sizes), 'jpeg_p95_bytes': percentile(sizes, .95),
        'payload_mbps': sum(sizes) * 8 / args.seconds / 1e6,
        'max_capture_gap_s': max(capture_gaps, default=None),
        'boot_ids_observed': sorted({r['boot_id'] for r in frame_rows if 'boot_id' in r}),
        'rssi_min_dbm': min((r['rssi_dbm'] for r in frame_rows if 'rssi_dbm' in r), default=None),
        'rssi_median_dbm': percentile([r['rssi_dbm'] for r in frame_rows if 'rssi_dbm' in r], .5),
        'wifi_disconnects_observed': max((r.get('wifi_disconnects', 0) for r in frame_rows), default=0)
        - min((r.get('wifi_disconnects', 0) for r in frame_rows), default=0),
        'wifi_disconnect_reasons': sorted({r['last_wifi_reason'] for r in frame_rows if r.get('last_wifi_reason')}),
        'initial_device_status': profile_status,
        'final_device_status': final_status,
        'tcp_no_delay_values': sorted({r['tcp_no_delay'] for r in frame_rows if 'tcp_no_delay' in r}),
        'network_modes': sorted({r['network_mode'] for r in frame_rows if 'network_mode' in r}),
        **measured,
        'collection_test_passed': not reasons, 'collection_test_issues': reasons,
        'criteria': '>=95% target mean FPS; >=90% target in each 10s window; no missing sequences/retries/stale/source missed slots; max capture gap <=2.1 target periods; max arrival pause <=500ms',
    }
    (root / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
