"""Run the actual hub script with a virtual clock and fake motors/byte stream."""
import runpy
import sys
import types
from collections import deque
from pathlib import Path
from types import SimpleNamespace

import pytest


def run_bridge(monkeypatch, packets):
    clock = SimpleNamespace(ms=0)
    scheduled = deque(packets)
    available = deque()
    motors = []
    output = []

    class Watch:
        def __init__(self):
            self.reset()

        def reset(self):
            self.started = clock.ms

        def time(self):
            return clock.ms - self.started

    class Motor:
        def __init__(self, *_):
            self.events = []
            motors.append(self)

        def dc(self, power):
            self.events.append((clock.ms, power))

        def brake(self):
            self.events.append((clock.ms, 0))

    class Poll:
        def register(self, _):
            pass

        def poll(self, timeout):
            if not available:
                clock.ms += timeout
            while scheduled and scheduled[0][0] <= clock.ms:
                available.extend(scheduled.popleft()[1])
            return [1] if available else []

    def read(count):
        assert count == 1 and available, 'No blocking reads allowed in hub loop'
        return bytes([available.popleft()])

    def wait(ms):
        clock.ms += ms
        assert clock.ms < 20000, 'Bridge failed to exit an abandoned session'

    modules = {
        'pybricks': {},
        'pybricks.parameters': {'Direction': SimpleNamespace(CLOCKWISE=1, COUNTERCLOCKWISE=-1),
                                'Port': SimpleNamespace(D='D', B='B')},
        'pybricks.pupdevices': {'DCMotor': Motor, 'Motor': Motor},
        'pybricks.tools': {'StopWatch': Watch, 'wait': wait},
        'usys': {'stdin': SimpleNamespace(buffer=SimpleNamespace(read=read)),
                 'stdout': SimpleNamespace(buffer=SimpleNamespace(write=output.append))},
        'uselect': {'poll': Poll},
    }
    for name, attributes in modules.items():
        module = types.ModuleType(name)
        module.__dict__.update(attributes)
        monkeypatch.setitem(sys.modules, name, module)
    runpy.run_path(str(Path(__file__).parents[1] / 'hub/main.py'))
    return clock.ms, motors, output


def test_abandoned_session_exits_after_five_seconds(monkeypatch):
    elapsed, motors, _ = run_bridge(monkeypatch, [])
    assert 5000 <= elapsed <= 5020
    assert all(events.events[-1][1] == 0 for events in motors)


def test_drive_brakes_at_one_second_then_idle_program_exits(monkeypatch):
    elapsed, motors, _ = run_bridge(monkeypatch, [(0, b'D\x96\x96')])
    assert 5000 <= elapsed <= 5050
    for motor in motors:
        movement = next(event for event in motor.events if event[1] == 50)
        stop = next(event for event in motor.events if event[1] == 0 and event[0] > movement[0])
        assert 1000 <= stop[0] - movement[0] <= 1020


def test_pings_keep_idle_session_alive_without_moving_motors(monkeypatch):
    elapsed, motors, output = run_bridge(monkeypatch, [(t, b'P') for t in range(0, 6001, 1000)])
    assert 11000 <= elapsed <= 11030
    assert output.count(b'PONG\n') == 7
    assert all(power == 0 for motor in motors for _, power in motor.events)


@pytest.mark.parametrize('tail', [b'D', b'D\x96'])
def test_truncated_packet_cannot_block_braking_or_idle_exit(monkeypatch, tail):
    elapsed, motors, _ = run_bridge(monkeypatch, [(0, b'D\x96\x96'), (800, tail)])
    assert 5000 <= elapsed <= 5050
    assert all(any(1000 <= t <= 1050 and power == 0 for t, power in motor.events) for motor in motors)


def test_expired_partial_packet_allows_next_complete_command(monkeypatch):
    elapsed, motors, _ = run_bridge(monkeypatch, [(0, b'D'), (1400, b'D\x96\x96')])
    assert 6400 <= elapsed <= 6450
    assert all(any(power == 50 for _, power in motor.events) for motor in motors)


def test_explicit_exit_brakes_and_ends_immediately(monkeypatch):
    elapsed, motors, _ = run_bridge(monkeypatch, [(0, b'D\x96\x96'), (100, b'X')])
    assert elapsed < 150
    assert all(motor.events[-1][1] == 0 for motor in motors)
