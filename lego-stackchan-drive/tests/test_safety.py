import asyncio
import io
import json
import time

import pygame
import pytest

from lego_stackchan_drive.core import Controls, Episode, Workers, inspect_episode


def test_expired_input_stops_until_fresh_sample_without_arming():
    control = Controls(25)
    control.camera_tick(time.monotonic())
    control.update((1, 0), True)
    assert control.command()[1] == (75, 75)
    assert control.command(control.updated + 0.26)[1] == (0, 0)
    assert control.drive_available
    control.refresh_action((1, 0))
    assert control.command()[1] == (75, 75)


@pytest.mark.parametrize(
    ("action", "expected"),
    [((1, 0), (75, 75)), ((-1, 0), (-75, -75)), ((0, 1), (-25, 25)), ((0, -1), (25, -25)),
     ((0.5, 0), (38, 38)), ((0.4, 1), (5, 55)), ((1, 1), (38, 75))],
)
def test_operator_corrected_directions(action, expected):
    controls = Controls(25)
    controls.camera_tick(time.monotonic())
    controls.update(action, True)
    assert controls.command()[1] == expected


def test_high_base_power_caps_throttle_without_reducing_steering():
    controls = Controls(40)
    controls.camera_tick(time.monotonic())
    controls.update((1, 0), True)
    assert controls.command()[1] == (100, 100)
    controls.update((0, 1), True)
    assert controls.command()[1] == (-40, 40)
    controls.update((1, 1), True)
    assert controls.command()[1] == (43, 100)


def test_lost_camera_stops_even_if_ui_keeps_updating():
    control = Controls()
    control.camera_tick(time.monotonic() - 1)
    control.update((1, 0), True)
    assert control.command()[1] == (0, 0)
    assert control.drive_available
    control.camera_tick(time.monotonic())
    assert control.command()[1] == (75, 75)


def test_ble_failure_reconnects_automatically_with_zero_startup(monkeypatch):
    clients = []

    class Client:
        last_pong_at = 0
        disconnected = False

        def __init__(self, **_):
            self.sent = []
            clients.append(self)

        async def connect(self):
            if len(clients) == 1:
                raise RuntimeError("link lost")
            return type("Hub", (), {"name": "test"})()

        async def drive(self, *wheels, **_):
            self.sent.append(wheels)
            if len(self.sent) == 2:
                worker.stop.set()

        async def ping(self):
            self.last_pong_at = time.monotonic()

        async def disconnect(self):
            self.disconnected = True

    monkeypatch.setattr("lego_stackchan_drive.core.PybricksHubClient", Client)
    worker = Workers(Controls(), "unused", "unused")
    monkeypatch.setattr(worker.stop, "wait", lambda _: False)
    worker.drive()
    assert len(clients) == 2 and all(c.disconnected for c in clients)
    assert clients[1].sent == [(0, 0), (0, 0)]
    assert worker.drive_error is None and worker.error is None and worker.interruptions == 1


def test_episode_keeps_capture_and_command_times_distinct(tmp_path):
    image = pygame.Surface((320, 240))
    image.fill((30, 120, 180))
    buffer = io.BytesIO()
    pygame.image.save(image, buffer, "frame.jpg")
    episode = Episode(tmp_path, "test road", 25)
    now = time.monotonic()
    episode.add(
        {
            "kind": "frame",
            "t": now + 0.03,
            "estimated_capture_t": now,
            "sensor_us": 100,
            "device_sent_us": 200,
            "sequence": 1,
            "jpeg": buffer.getvalue(),
        }
    )
    episode.add(
        {
            "kind": "command",
            "t": now + 0.04,
            "send_started": now + 0.035,
            "action": [0.5, 0],
            "wheels": [12, 12],
        }
    )
    path = episode.close("diagnostic")
    summary = inspect_episode(path)
    assert summary["frames"] == summary["nonzero_commands"] == 1
    rows = [json.loads(line) for line in (path / "events.jsonl").read_text().splitlines()]
    assert rows[0]["estimated_capture_t"] < rows[0]["t"] < rows[1]["t"]


def test_failed_capture_is_not_a_successful_empty_dataset(tmp_path):
    episode = Episode(tmp_path, "empty", 25)
    episode.close("interrupted")
    with pytest.raises(ValueError, match="no camera frames"):
        inspect_episode(episode.path)


def test_ble_shutdown_always_disconnects(monkeypatch):
    class Client:
        disconnected = False

        def __init__(self):
            self.sent = []

        async def connect(self):
            return type("Hub", (), {"name": "test"})()

        async def drive(self, *wheels):
            self.sent.append(wheels)
            worker.stop.set()

        async def ping(self):
            pass

        async def disconnect(self):
            self.disconnected = True

    client = Client()
    monkeypatch.setattr("lego_stackchan_drive.core.PybricksHubClient", lambda **_: client)
    worker = Workers(Controls(), "unused", "unused")
    asyncio.run(worker.drive_loop())
    assert client.disconnected and client.sent == [(0, 0)]


def test_slow_ack_preserves_arm_without_extra_stop_or_cancel(monkeypatch):
    monkeypatch.setattr("lego_stackchan_drive.core.BLE_SLOW_REPLY_S", 0.01)

    class Client:
        def __init__(self):
            self.sent = []
            self.cancelled = False
            self.last_pong_at = time.monotonic()

        async def drive(self, *wheels):
            self.sent.append(wheels)
            if len(self.sent) == 1:
                try:
                    await asyncio.sleep(0.03)
                except asyncio.CancelledError:
                    self.cancelled = True
                    raise

    controls = Controls()
    controls.camera_tick(time.monotonic())
    controls.update((1, 0), True)
    worker = Workers(controls, "unused", "unused")
    worker.ready = True
    client = Client()
    asyncio.run(worker.send_drive(client, (1, 0), (25, 25)))
    assert client.sent == [(25, 25)]
    assert not client.cancelled
    assert controls.drive_available and controls.command()[1] == (75, 75)
    assert worker.ready and not worker.stop.is_set() and worker.error is None
    assert worker.interruptions == 0
    assert list(worker.events.queue)[-1]["delayed_ack"]


def test_dead_ble_write_stops_on_heartbeat_deadline(monkeypatch):
    monkeypatch.setattr("lego_stackchan_drive.core.HEARTBEAT_TIMEOUT_S", 0.03)

    class Client:
        last_pong_at = time.monotonic()
        cancelled = False

        async def drive(self, *_wheels):
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                self.cancelled = True
                raise

    controls = Controls()
    controls.camera_tick(time.monotonic())
    controls.update((1, 0), True)
    worker = Workers(controls, "unused", "unused")
    worker.ready = True
    client = Client()
    started = time.monotonic()
    with pytest.raises(RuntimeError, match="heartbeat missing"):
        asyncio.run(worker.send_drive(client, (1, 0), (50, 50)))
    assert time.monotonic() - started < .15
    assert client.cancelled and not worker.ready and not controls.drive_available


def test_pending_write_stays_available_while_heartbeat_replies_arrive(monkeypatch):
    monkeypatch.setattr("lego_stackchan_drive.core.HEARTBEAT_TIMEOUT_S", .06)
    monkeypatch.setattr("lego_stackchan_drive.core.BLE_SLOW_REPLY_S", .01)

    class Client:
        last_pong_at = time.monotonic()

        async def drive(self, *_wheels):
            for _ in range(5):
                await asyncio.sleep(.02)
                self.last_pong_at = time.monotonic()

    controls = Controls()
    controls.camera_tick(time.monotonic())
    controls.update((1, 0), True)
    worker = Workers(controls, "unused", "unused")
    worker.ready = True
    asyncio.run(worker.send_drive(Client(), (1, 0), (50, 50)))
    assert controls.drive_available and worker.ready and worker.interruptions == 0
    assert list(worker.events.queue)[-1]["delayed_ack"]


def test_busy_hub_never_retries_motion_and_requires_consumption_ack():
    from lego_stackchan_drive.vendor.link import HubBusyError

    class Client:
        def __init__(self):
            self.sent = []
            self.ponged = False
            self.last_pong_at = time.monotonic()

        async def drive(self, *wheels):
            self.sent.append(wheels)
            if len(self.sent) <= 2:
                raise HubBusyError('full')

        async def ping(self, timeout):
            assert not worker.ready and not controls.drive_available
            self.ponged = True

    controls = Controls()
    controls.camera_tick(time.monotonic())
    controls.update((1, 0), True)
    worker = Workers(controls, 'unused', 'unused')
    worker.ready = True
    client = Client()
    asyncio.run(worker.send_drive(client, (1, 0), (25, 25)))
    assert client.sent == [(25, 25), (0, 0), (0, 0)]
    assert client.ponged and worker.ready and not controls.drive_available
    assert controls.command()[1] == (0, 0) and worker.interruptions == 1
    events = list(worker.events.queue)
    assert any(event['kind'] == 'hub_busy' for event in events)
    assert all(e['wheels'] == [0, 0] for e in events if e['kind'] == 'command')


def test_persistent_busy_hub_fails_with_bounded_stop_attempts():
    from lego_stackchan_drive.vendor.link import HubBusyError

    class Client:
        def __init__(self):
            self.sent = []
            self.last_pong_at = time.monotonic()

        async def drive(self, *wheels):
            self.sent.append(wheels)
            raise HubBusyError('full')

    worker = Workers(Controls(), 'unused', 'unused')
    client = Client()
    with pytest.raises(RuntimeError, match='three stop attempts'):
        asyncio.run(worker.send_drive(client, (1, 0), (25, 25)))
    assert client.sent == [(25, 25), (0, 0), (0, 0), (0, 0)]
    assert not worker.ready and not worker.controls.drive_available


def test_hub_busy_code_is_specific_and_stopped_program_blocks_writes():
    from bleak.exc import BleakGATTProtocolError

    from lego_stackchan_drive.vendor.link import HubBusyError, LinkError, PybricksHubClient

    class Gatt:
        is_connected = True
        code = 0x81
        writes = 0

        async def write_gatt_char(self, *_args, **_kwargs):
            self.writes += 1
            raise BleakGATTProtocolError(self.code)

    c = PybricksHubClient()
    c._client = Gatt()
    with pytest.raises(HubBusyError, match='buffer full'):
        asyncio.run(c.drive(0, 0))
    c._client.code = 0x80
    with pytest.raises(BleakGATTProtocolError):
        asyncio.run(c.drive(0, 0))
    c._on_notification(None, bytearray(b'\x01READY\n'))
    c._on_notification(None, bytearray(b'\x01OSError: motor disconnected\n'))
    c._on_notification(None, bytearray(b'\x00\x00\x00\x00\x00'))
    with pytest.raises(LinkError, match='motor disconnected'):
        asyncio.run(c.drive(0, 0))
    assert c._client.writes == 2


def test_drive_does_not_request_or_wait_for_consumption_reply():
    from lego_stackchan_drive.vendor.link import PybricksHubClient

    async def scenario():
        client = PybricksHubClient()

        class Gatt:
            is_connected = True

            async def write_gatt_char(self, _uuid, packet, response):
                assert response and packet == b'\x06D}\x64'

        client._client = Gatt()
        client._on_notification(None, bytearray(b'\x01PONG\n'))
        command = asyncio.create_task(client.drive(25, 0))
        await asyncio.wait_for(command, .1)

    asyncio.run(scenario())


def test_heartbeat_request_does_not_block_drive_and_reply_is_observed():
    from lego_stackchan_drive.vendor.link import PybricksHubClient

    async def scenario():
        client = PybricksHubClient()

        class Gatt:
            is_connected = True

            async def write_gatt_char(self, _uuid, packet, response):
                assert response and packet == b'\x06D}\x64P'

        client._client = Gatt()
        await asyncio.wait_for(client.drive(25, 0, heartbeat=True), .1)
        assert client.last_pong_at == 0
        client._on_notification(None, bytearray(b'\x01PO'))
        client._on_notification(None, bytearray(b'\x01NG\n'))
        assert client.last_pong_at > 0

    asyncio.run(scenario())


def test_latest_input_replaces_intermediate_commands_without_queue(monkeypatch):
    async def scenario():
        class Client:
            def __init__(self):
                self.sent = []
                self.last_pong_at = 0

            async def connect(self):
                return type('Hub', (), {'name': 'test'})()

            async def ping(self):
                self.last_pong_at = time.monotonic()

            async def drive(self, *wheels, **_kwargs):
                self.sent.append(wheels)
                if len(self.sent) == 2:
                    for value in (.8, .4, .2):
                        controls.refresh_action((value, 0))
                        await asyncio.sleep(.005)
                elif len(self.sent) == 3:
                    worker.stop.set()

            async def disconnect(self):
                pass

        client = Client()
        monkeypatch.setattr('lego_stackchan_drive.core.PybricksHubClient', lambda **_: client)
        controls = Controls()
        controls.camera_tick(time.monotonic())
        controls.update((1, 0), True)
        worker = Workers(controls, 'unused', 'unused')
        await worker.drive_loop()
        assert client.sent == [(0, 0), (75, 75), (15, 15)]

    asyncio.run(scenario())


def test_missing_heartbeat_blocks_drive_and_disconnects_without_stopping_camera(monkeypatch):
    monkeypatch.setattr('lego_stackchan_drive.core.HEARTBEAT_PERIOD_S', .01)
    monkeypatch.setattr('lego_stackchan_drive.core.HEARTBEAT_TIMEOUT_S', .03)
    monkeypatch.setattr('lego_stackchan_drive.core.DRIVE_HZ', 100)

    class Client:
        last_pong_at = 0
        disconnected = False
        heartbeat_requests = 0

        async def connect(self):
            return type('Hub', (), {'name': 'test'})()

        async def drive(self, *_wheels, heartbeat=False):
            self.heartbeat_requests += heartbeat

        async def ping(self):
            self.last_pong_at = time.monotonic()

        async def disconnect(self):
            self.disconnected = True

    client = Client()
    monkeypatch.setattr('lego_stackchan_drive.core.PybricksHubClient', lambda **_: client)
    controls = Controls()
    worker = Workers(controls, 'unused', 'unused')
    with pytest.raises(RuntimeError, match='heartbeat missing'):
        asyncio.run(worker.drive_loop())
    assert client.heartbeat_requests >= 1 and client.disconnected
    assert not controls.drive_available and not worker.stop.is_set()


def test_bridge_ping_without_reply_has_bounded_failure():
    from lego_stackchan_drive.vendor.link import LinkError, PybricksHubClient

    async def scenario():
        client = PybricksHubClient()

        class Gatt:
            is_connected = True

            async def write_gatt_char(self, *_args, **_kwargs):
                pass

        client._client = Gatt()
        with pytest.raises(LinkError, match='command consumption'):
            await client.ping(timeout=.01)

    asyncio.run(scenario())


def test_shutdown_disconnects_even_when_stop_write_never_acknowledges():
    from lego_stackchan_drive.vendor.link import PybricksHubClient

    class Gatt:
        is_connected = True
        disconnected = False
        write_cancelled = False

        async def write_gatt_char(self, *_args, **_kwargs):
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                self.write_cancelled = True
                raise

        async def disconnect(self):
            self.disconnected = True
            self.is_connected = False

    client = PybricksHubClient()
    gatt = Gatt()
    client._client = gatt
    started = time.monotonic()
    asyncio.run(client.disconnect())
    assert time.monotonic() - started < 1.5
    assert gatt.write_cancelled and gatt.disconnected and client._client is None
