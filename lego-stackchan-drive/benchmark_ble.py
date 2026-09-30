"""Explicit zero-power test of the production direct-BLE 10 Hz loop.

Leaves the existing camera viewer running. Never arms or issues nonzero power.
Diagnostic results stay separate from training recordings.
"""
import argparse
import asyncio
import json
import queue
import time
from itertools import pairwise
from pathlib import Path

from lego_stackchan_drive.core import (
    DRIVE_HZ,
    HEARTBEAT_PERIOD_S,
    HEARTBEAT_TIMEOUT_S,
    Controls,
    Workers,
)
from lego_stackchan_drive.metrics import percentile


async def measure(seconds, hub_name):
    worker = Workers(Controls(), 'unused', 'unused', hub_name=hub_name)
    events = []
    task = asyncio.create_task(worker.drive_loop())
    started = time.monotonic()
    first_command = None
    error = None
    try:
        while not task.done():
            while True:
                try:
                    event = worker.events.get_nowait()
                except queue.Empty:
                    break
                events.append(event)
                if event['kind'] == 'command':
                    assert event['wheels'] == [0, 0], 'Diagnostic must never move motors'
                    first_command = first_command or event['send_started']
            if first_command and time.monotonic() - first_command >= seconds:
                worker.stop.set()
            elif not first_command and time.monotonic() - started > 25:
                raise TimeoutError('No confirmed commands after connection deadline')
            await asyncio.sleep(.01)
        await task
    except Exception as exc:  # noqa: BLE001 - save hardware failures in the diagnostic
        error = str(exc) or type(exc).__name__
    finally:
        worker.stop.set()
        try:
            await asyncio.wait_for(task, 5)
        except Exception as exc:  # noqa: BLE001 - report shutdown failures too
            error = error or str(exc) or type(exc).__name__
        while not worker.events.empty():
            events.append(worker.events.get_nowait())
    commands = [event for event in events if event['kind'] == 'command']
    intervals = [b['send_started'] - a['send_started'] for a, b in pairwise(commands)]
    acknowledgments = [event['t'] - event['send_started'] for event in commands]
    heartbeats = [event for event in events if event['kind'] == 'hub_heartbeat']
    rate = (len(commands) - 1) / sum(intervals) if intervals else 0
    report = {
        'path': 'Mac directly to LEGO hub over BLE', 'target_hz': DRIVE_HZ,
        'requested_seconds': seconds, 'zero_power_only': True,
        'control_mode': 'Open-loop commands; periodic heartbeat; slow ACKs diagnostic only; one write in flight',
        'heartbeat_period_s': HEARTBEAT_PERIOD_S, 'heartbeat_timeout_s': HEARTBEAT_TIMEOUT_S,
        'commands': len(commands), 'effective_hz': rate,
        'transport_acknowledged': sum(event.get('transport_ack', False) for event in commands),
        'write_ack_p95_ms': percentile(acknowledgments, .95) * 1000 if acknowledgments else None,
        'write_ack_max_ms': max(acknowledgments, default=0) * 1000,
        'heartbeat_requests': sum(event.get('heartbeat_requested', False) for event in commands),
        'heartbeat_replies': len(heartbeats),
        'command_interval_max_ms': max(intervals, default=0) * 1000,
        'delayed_write_acks': sum(event.get('delayed_ack', False) for event in commands),
        'busy_events': sum(event['kind'] == 'hub_busy' for event in events),
        'heartbeat_gap_max_ms': max((b['t'] - a['t'] for a, b in pairwise(heartbeats)), default=0) * 1000,
        'stability_passed': bool(not error and commands and not worker.interruptions),
        'error': error,
        'passed': bool(not error and len(commands) >= seconds * DRIVE_HZ * .98
                       and 9.8 <= rate <= 10.2
                       and all(event.get('transport_ack') for event in commands)
                       and not worker.interruptions),
    }
    directory = Path('.local/ble-tests') / time.strftime('%Y%m%d-%H%M%S-open-loop-10hz')
    directory.mkdir(parents=True)
    (directory / 'events.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in events))
    (directory / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'report_path': str(directory / 'report.json'), **report}, indent=2))
    return report['passed']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=float, default=120)
    parser.add_argument('--hub-name')
    args = parser.parse_args()
    if args.seconds < 1:
        parser.error('--seconds must be at least 1')
    raise SystemExit(0 if asyncio.run(measure(args.seconds, args.hub_name)) else 1)


if __name__ == '__main__':
    main()
