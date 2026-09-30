"""Panel-owned ACT runtime; reuse the existing controller and motor watchdogs."""

import fcntl
import http.client
import json
import signal
import subprocess
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .policy import DEFAULT_CHECKPOINT, validate_checkpoint

PROJECT = Path(__file__).resolve().parents[2]


def lease_alive(path, now=None):
    if path is None:
        return True
    try:
        age = (time.time() if now is None else now) - path.stat().st_mtime
        return 0 <= age < 2
    except OSError:
        return False


@contextmanager
def runtime_lock(project=PROJECT):
    path = project / '.local/drive-runtime.lock'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError('A LEGO driving window is already running; close it first') from error
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def write_status(path, **state):
    if path is not None:
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'updated': time.time(), **state}))
        temporary.replace(path)


class Cancelled(Exception):
    pass


class DriveMode:
    def __init__(self, client, config, *, project=PROJECT):
        self.client, self.config, self.project = client, Path(config).resolve(), project
        self.lock = threading.Lock()
        self.cancel = threading.Event()
        self.thread = None
        self.process = None
        self.status_path = self.lease = None
        self.current = {'active': False, 'phase': 'idle', 'error': ''}

    def _state(self, **fields):
        with self.lock:
            self.current.update(fields)

    def state(self):
        with self.lock:
            state = dict(self.current)
            path = self.status_path
        if state['active'] and path and path.exists():
            try:
                runtime = json.loads(path.read_text())
                if 0 <= time.time() - runtime['updated'] < 2:
                    state['runtime'] = runtime
            except (OSError, ValueError, KeyError):
                pass
        return state

    def start(self):
        with self.lock:
            if self.current['active']:
                return False
            self.current = {'active': True, 'phase': 'preparing', 'error': ''}
            self.status_path = self.lease = None
            self.cancel.clear()
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()
        return True

    def stop(self):
        self.cancel.set()
        with self.lock:
            if self.current['active']:
                self.current['phase'] = 'stopping'
            if self.lease:
                self.lease.unlink(missing_ok=True)
        return self.state()

    def _head_mode(self, release):
        end = time.monotonic() + 40
        requested = False
        while time.monotonic() < end:
            if not release and self.cancel.is_set():
                raise Cancelled()
            try:
                if not requested:
                    self.client.set_head('release' if release else 'resume')
                    requested = True
                state = self.client.head_state()
                if (not state.get('restarting') and state.get('manual_posing') == release
                        and state.get('servo_power_verified')
                        and state.get('servo_power_enabled') == (not release)):
                    return
            except (OSError, RuntimeError, http.client.HTTPException):
                pass
            time.sleep(.25)
        raise RuntimeError('Head mode not confirmed; check Stack Chan')

    def _stop_process(self):
        process = self.process
        if process is not None and process.poll() is None:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=12)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
                # The hub stops independently when commands cease.
                time.sleep(1.1)

    def _run(self):
        touched_head = False
        error = ''
        log = None
        try:
            selection_path = self.project / '.local/drive-model.json'
            selected = (json.loads(selection_path.read_text())['checkpoint']
                        if selection_path.exists() else DEFAULT_CHECKPOINT)
            checkpoint, _ = validate_checkpoint(self.project / selected, 25)
            if not (self.project / 'training/.venv/bin/python').is_file():
                raise RuntimeError('Training runtime is missing; run ./app build-training')
            with runtime_lock(self.project):
                pass  # Refuse an existing CLI driver before changing its camera pose.
            root = self.project / '.local/panel-drive' / uuid.uuid4().hex
            root.mkdir(parents=True)
            self.status_path, self.lease = root / 'status.json', root / 'lease'
            face = self.client.state()
            touched_head = True
            self._head_mode(False)
            self.client.send(emotion=face['emotion'], animated=face['animated'],
                             auto_cycle=face['auto_cycle'])
            self.client._request('/camera', {'fps': 10, 'quality': 85})
            if self.cancel.is_set():
                raise Cancelled()
            self.lease.touch()
            log = (root / 'driver.log').open('w')
            self.process = subprocess.Popen([
                str(self.project / '.venv/bin/python'), '-m', 'lego_stackchan_drive.main',
                'run', '--policy', str(checkpoint), '--camera-config', str(self.config),
                '--panel-lease', str(self.lease), '--status-file', str(self.status_path),
            ], cwd=self.project, stdout=log, stderr=subprocess.STDOUT)
            self._state(phase='running')
            while self.process.poll() is None and not self.cancel.wait(.25):
                self.lease.touch()
            if not self.cancel.is_set() and self.process.poll() not in (None, 0):
                raise RuntimeError('Driving window exited with an error; see ' + str(root / 'driver.log'))
        except Cancelled:
            pass
        except Exception as exc:  # noqa: BLE001 - surface failures and always stop hardware
            error = str(exc)
        finally:
            self._state(phase='stopping')
            try:
                if self.lease:
                    self.lease.unlink(missing_ok=True)
                self._stop_process()
                if touched_head:
                    try:
                        face = self.client.state()
                    except (OSError, RuntimeError, http.client.HTTPException):
                        face = None
                    self._head_mode(True)
                    if face:
                        self.client.send(emotion=face['emotion'], animated=face['animated'],
                                         auto_cycle=face['auto_cycle'])
                    self.client._request('/camera', {'fps': 10, 'quality': 85})
            except Exception as exc:  # noqa: BLE001 - report an incomplete shutdown explicitly
                error = (error + '; ' if error else '') + 'Cleanup: ' + str(exc)
            finally:
                if log:
                    log.close()
                self._state(active=False, phase='error' if error else 'idle', error=error)

    def close(self):
        self.stop()
        if self.thread:
            self.thread.join(timeout=60)
