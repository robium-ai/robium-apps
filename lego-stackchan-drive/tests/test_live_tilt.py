import threading
import time

from lego_stackchan_drive import core


def wait_for(check):
    deadline = time.monotonic() + 3
    while not check():
        assert time.monotonic() < deadline
        time.sleep(.01)


def test_live_tilt_moves_in_worker_holds_and_clamps(monkeypatch):
    class Head:
        def __init__(self, *_):
            self.pitch = 0
            self.sent = []
            self.closed = False

        def send(self, pan, tilt):
            self.sent.append((pan, tilt))
            self.pitch = tilt * 85
            return self.hold()

        def hold(self):
            return {'yaw_deg': 0, 'pitch_deg': self.pitch}

        def close(self):
            self.closed = True

    client = Head()
    monkeypatch.setattr(core, 'HeadClient', lambda *_: client)
    worker = core.Workers(core.Controls(), 'unused', 'unused')
    thread = threading.Thread(target=worker.head)
    thread.start()
    try:
        wait_for(lambda: worker.head_ready)
        worker.adjust_tilt(5)
        wait_for(lambda: worker.head_state['pitch_deg'] == 5)
        assert worker.head_ready  # Moving tilt does not pause driving.
        worker.adjust_tilt(100)
        wait_for(lambda: worker.head_state['pitch_deg'] == 85)
        worker.adjust_tilt(-200)
        wait_for(lambda: worker.head_state['pitch_deg'] == 0)
        assert all(pan == 0 and 0 <= tilt <= 1 for pan, tilt in client.sent)
        time.sleep(.8)
        count = len(client.sent)
        time.sleep(.15)
        assert len(client.sent) == count  # No repeated motion when settled.
    finally:
        worker.stop.set()
        thread.join(3)
    assert not thread.is_alive() and client.closed


def test_video_only_and_unready_head_ignore_tilt():
    worker = core.Workers(core.Controls(), 'unused', 'unused')
    worker.adjust_tilt(5)
    assert worker.head_target_tilt == 0
    worker.head_ready = True
    worker.video_only = True
    worker.adjust_tilt(5)
    assert worker.head_target_tilt == 0


def test_head_feedback_failure_disables_driving(monkeypatch):
    class Broken:
        def __init__(self, *_):
            pass

        def send(self, *_):
            raise OSError('connection lost')

        def close(self):
            pass

        def hold(self):
            pass

    monkeypatch.setattr(core, 'HeadClient', Broken)
    worker = core.Workers(core.Controls(), 'unused', 'unused')
    worker.head_ready = True
    worker.controls.update((1, 0), True)
    worker.head()
    assert not worker.head_ready and not worker.controls.drive_available
    assert worker.head_error
