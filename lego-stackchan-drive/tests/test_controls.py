import time

from lego_stackchan_drive.core import Controls
from lego_stackchan_drive.vendor.gamepad import read_gamepad


class Pad:
    def __init__(self, axes, stop=False):
        self.axes, self.stop = axes, stop

    def get_numaxes(self):
        return len(self.axes)

    def get_axis(self, index):
        return self.axes[index]

    def get_numbuttons(self):
        return 1

    def get_button(self, _index):
        return self.stop

    def get_numhats(self):
        return 0


def test_right_stick_horizontal_steers_without_moving_camera():
    reading = read_gamepad(Pad([0, 0, 1, -1]))
    assert (reading.throttle, reading.steer) == (0, 1)
    assert (reading.pan, reading.tilt) == (0, 0)


def test_left_stick_vertical_controls_throttle_only():
    reading = read_gamepad(Pad([1, -1, 0, 0]))
    assert (reading.throttle, reading.steer) == (1, 0)
    assert (reading.pan, reading.tilt) == (0, 0)


def test_unused_stick_axes_are_ignored():
    reading = read_gamepad(Pad([1, 0, 0, -1]))
    assert (reading.throttle, reading.steer, reading.pan, reading.tilt) == (0, 0, 0, 0)


def test_throttle_and_steering_use_separate_sticks_together():
    reading = read_gamepad(Pad([0, -1, -1, 0]))
    assert (reading.throttle, reading.steer) == (1, -1)


def test_a_button_does_not_change_drive_input():
    reading = read_gamepad(Pad([1, -1, 1, -1], stop=True))
    assert (reading.throttle, reading.steer, reading.pan, reading.tilt) == (1, 1, 0, 0)


def test_recording_triggers_are_independent_of_drive_and_a_button():
    for left, right in ((1, -1), (-1, 1), (1, 1)):
        reading = read_gamepad(Pad([0, -1, .5, 0, left, right]))
        assert reading.record_held and reading.throttle == 1 and reading.steer > 0
        with_a = read_gamepad(Pad([0, -1, .5, 0, left, right], stop=True))
        assert with_a == reading
    assert not read_gamepad(Pad([0, 0, 0, 0, -1, -1])).record_held
    assert not read_gamepad(Pad([0, 0, 0, 0])).record_held
    assert not read_gamepad(Pad([0, 0, 0, 0, -.8, -.8])).record_held


def test_mapped_trigger_zero_does_not_record_before_raw_axes_initialize():
    reading = read_gamepad(Pad([0] * 6), trigger_values=(0, 0))
    assert not reading.record_held


def test_startup_center_retries_zero_and_ignores_joystick_head_action(monkeypatch):
    from lego_stackchan_drive.core import Workers

    sent = []

    class Client:
        def __init__(self, *_args):
            pass

        def send(self, pan, tilt):
            sent.append((pan, tilt))
            if len(sent) == 1:
                raise TimeoutError("delayed Wi-Fi")
            return {"yaw_deg": 0, "pitch_deg": 0}

        def close(self):
            pass

        def hold(self):
            return self.send(0, 0)

    monkeypatch.setattr("lego_stackchan_drive.core.HeadClient", Client)
    control = Controls()
    control.camera_tick(time.monotonic())
    control.update((1, 1), True)
    worker = Workers(control, "unused", "unused")
    import threading

    thread = threading.Thread(target=worker.head)
    thread.start()
    try:
        deadline = time.monotonic() + 3
        while not worker.head_ready and time.monotonic() < deadline:
            time.sleep(.01)
    finally:
        worker.stop.set()
        thread.join(3)
    assert not thread.is_alive()
    assert len(sent) > 1
    assert all(action == (0, 0) for action in sent)
    assert worker.error is None and worker.head_ready


def test_video_timeout_reconnects_and_accepts_fresh_input(monkeypatch):
    from lego_stackchan_drive.core import Workers

    calls = []

    def stream(*_args):
        calls.append(1)
        if len(calls) == 1:
            raise TimeoutError("Wi-Fi pause")
        now = time.monotonic()
        yield {
            "kind": "frame",
            "t": now,
            "device_sent_us": 1000000,
            "sensor_us": 950000,
            "sequence": 1,
        }
        worker.stop.set()

    monkeypatch.setattr("lego_stackchan_drive.core.frames", stream)
    controls = Controls()
    controls.update((1, 0), True)
    worker = Workers(controls, "unused", "unused")
    worker.camera()
    assert len(calls) == 2 and worker.error is None
    assert not controls.drive_available
    controls.update((.5, 0), True)
    assert controls.command()[1] == (38, 38)
    assert worker.latest["stream_generation"] == 1
    assert worker.interruptions == 1


def test_absolute_client_checks_firmware_without_moving(monkeypatch):
    import json

    from lego_stackchan_drive.head import HeadClient

    sent = []

    class Connection:
        def __init__(self, *_args, **_kwargs):
            pass

        def request(self, _method, _path, body, _headers):
            sent.append(json.loads(body))

        def getresponse(self):
            class Response:
                status = 200

                def read(self, _count):
                    return b'{"control_mode":"absolute"}'

            return Response()

    monkeypatch.setattr("lego_stackchan_drive.head.http.client.HTTPConnection", Connection)
    client = HeadClient("http://camera/stream", "test")
    client.send(0.5, 0.25)
    client.send(0, 0)
    assert [row["mode"] for row in sent] == ["hold", "absolute", "absolute"]
    assert sent[0]["pan"] == sent[0]["tilt"] == 0
    assert sent[-1]["pan"] == sent[-1]["tilt"] == 0
