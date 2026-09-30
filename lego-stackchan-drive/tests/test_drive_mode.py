import json
import os
import subprocess
import threading
import time

import pytest

from lego_stackchan_drive import drive_mode
from lego_stackchan_drive.drive_mode import DriveMode, lease_alive, runtime_lock, write_status


def test_missing_and_expired_panel_lease_stops_driver(tmp_path):
    lease = tmp_path / 'lease'
    assert lease_alive(None)
    assert not lease_alive(lease)
    lease.touch()
    now = time.time()
    os.utime(lease, (now, now))
    assert lease_alive(lease, now + 1.9)
    assert not lease_alive(lease, now + 2)
    assert not lease_alive(lease, now - 1)


def test_duplicate_runtime_cannot_own_lego(tmp_path):
    with (runtime_lock(tmp_path), pytest.raises(RuntimeError, match='already running'),
          runtime_lock(tmp_path)):
        pass
    with runtime_lock(tmp_path):
        pass


def test_atomic_status_and_stale_status_not_reported_as_ready(tmp_path):
    path = tmp_path / 'status.json'
    write_status(path, policy_ready=True)
    manager = DriveMode(None, tmp_path / 'config', project=tmp_path)
    manager.status_path = path
    manager.current['active'] = True
    assert manager.state()['runtime']['policy_ready']
    path.write_text(json.dumps({'updated': time.time() - 3, 'policy_ready': True}))
    assert 'runtime' not in manager.state()


class Face:
    def state(self):
        return {'emotion': 'happy', 'animated': True, 'auto_cycle': False}

    def send(self, **kwargs):
        pass

    def _request(self, *args):
        pass


def setup_manager(tmp_path, monkeypatch):
    python = tmp_path / 'training/.venv/bin/python'
    python.parent.mkdir(parents=True)
    python.touch()
    monkeypatch.setattr(drive_mode, 'validate_checkpoint', lambda *args: (tmp_path / 'checkpoint', {}))
    return DriveMode(Face(), tmp_path / 'camera.json', project=tmp_path)


def test_stop_during_preparation_never_launches_driver_and_releases_head(tmp_path, monkeypatch):
    manager = setup_manager(tmp_path, monkeypatch)
    entered = threading.Event()
    calls = []

    def head(release):
        calls.append(release)
        if not release:
            entered.set()
            manager.cancel.wait(2)
            raise drive_mode.Cancelled()

    manager._head_mode = head
    monkeypatch.setattr(drive_mode.subprocess, 'Popen', lambda *a, **kw: pytest.fail('Should not launch'))
    assert manager.start()
    assert entered.wait(1)
    assert not manager.start()
    manager.close()
    assert calls == [False, True]
    assert not manager.state()['active']


def test_process_failure_releases_head_and_reports_error(tmp_path, monkeypatch):
    manager = setup_manager(tmp_path, monkeypatch)
    calls, launches = [], []
    manager._head_mode = lambda release: calls.append(release)

    class Failed:
        def poll(self):
            return 1

    def launch(args, **kwargs):
        launches.append(args)
        return Failed()

    monkeypatch.setattr(drive_mode.subprocess, 'Popen', launch)
    manager.start()
    manager.thread.join(2)
    assert not manager.thread.is_alive()
    assert calls == [False, True]
    assert '--policy' in launches[0] and '--panel-lease' in launches[0]
    assert manager.state()['phase'] == 'error'
    assert not manager.lease.exists()


def test_stop_escalates_if_driver_does_not_exit(tmp_path, monkeypatch):
    manager = DriveMode(None, tmp_path / 'config')
    calls = []

    class Stuck:
        def poll(self):
            return None

        def send_signal(self, sig):
            calls.append('interrupt')

        def wait(self, timeout):
            if timeout == 12:
                raise subprocess.TimeoutExpired('driver', timeout)
            calls.append('wait')

        def kill(self):
            calls.append('kill')

    manager.process = Stuck()
    monkeypatch.setattr(drive_mode.time, 'sleep', lambda seconds: calls.append(seconds))
    manager._stop_process()
    assert calls == ['interrupt', 'kill', 'wait', 1.1]
