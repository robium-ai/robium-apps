from __future__ import annotations

import asyncio
import time
from unittest.mock import Mock

import pytest

import stackchan_er2.lego as lego_module
from stackchan_er2.config import LEGO_DIRECTIONS, LEGO_POWER
from stackchan_er2.lego import (
    COMMAND_WRITE_STDIN,
    DRIVE,
    PYBRICKS_COMMAND_EVENT_CHAR_UUID,
    HubCandidate,
    LegoDriveSession,
    LegoError,
    PybricksHubClient,
    choose_candidate,
    encode_drive,
    wheels_for_direction,
)


def test_all_semantic_directions_have_calibrated_wheel_powers() -> None:
    assert set(LEGO_DIRECTIONS) == {"forward", "backward", "left", "right", "stop"}
    assert wheels_for_direction("forward") == (-LEGO_POWER, -LEGO_POWER)
    assert wheels_for_direction("backward") == (LEGO_POWER, LEGO_POWER)
    assert wheels_for_direction("left") == (-LEGO_POWER, LEGO_POWER)
    assert wheels_for_direction("right") == (LEGO_POWER, -LEGO_POWER)
    assert wheels_for_direction("stop") == (0, 0)


def test_drive_packet_is_fixed_width_and_bounded() -> None:
    assert encode_drive(-LEGO_POWER, LEGO_POWER) == DRIVE + bytes(
        (100 - LEGO_POWER, 100 + LEGO_POWER)
    )
    with pytest.raises(ValueError):
        encode_drive(-101, 0)
    with pytest.raises(TypeError):
        encode_drive(True, 0)


def test_unknown_direction_is_rejected() -> None:
    with pytest.raises(LegoError, match="unknown LEGO direction"):
        wheels_for_direction("around")


def test_hub_selection_requires_a_name_when_discovery_is_ambiguous() -> None:
    hubs = [
        HubCandidate("Red", "one", Mock()),
        HubCandidate("Blue", "two", Mock()),
    ]
    assert choose_candidate(hubs, "red").address == "one"
    with pytest.raises(LegoError, match="More than one"):
        choose_candidate(hubs)


def test_missing_hub_has_an_actionable_error() -> None:
    with pytest.raises(LegoError, match="Turn the hub on"):
        choose_candidate([])


class FakeClient:
    def __init__(self, **_kwargs: object) -> None:
        self.candidate = HubCandidate("Fake LEGO", "fake", Mock())
        self.writes: list[tuple[int, int]] = []
        self.disconnected = False

    async def connect(self) -> HubCandidate:
        return self.candidate

    async def drive(self, left: int, right: int) -> None:
        self.writes.append((left, right))

    async def disconnect(self, *, stop_program: bool = True) -> None:
        self.disconnected = True


def test_drive_session_streams_motion_then_transmitted_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lego_module, "LEGO_MOVE_SECONDS", 0.02)
    client = FakeClient()
    session = LegoDriveSession(client_factory=lambda **_kwargs: client)
    try:
        assert session.start(timeout=1).hub_name == "Fake LEGO"
        result = session.drive("forward")

        assert result["status"] == "succeeded"
        assert result["stopped"] is True
        movement_index = client.writes.index((-LEGO_POWER, -LEGO_POWER))
        assert (0, 0) in client.writes[movement_index + 1 :]
    finally:
        session.close()
    assert client.disconnected is True


def test_stop_command_does_not_wait_for_motion_duration() -> None:
    client = FakeClient()
    session = LegoDriveSession(client_factory=lambda **_kwargs: client)
    try:
        session.start(timeout=1)
        started = time.monotonic()
        result = session.drive("stop")
        elapsed = time.monotonic() - started
    finally:
        session.close()

    assert result["duration_seconds"] == 0.0
    assert elapsed < 0.5


def test_pybricks_client_wraps_drive_packet_as_stdin() -> None:
    class FakeBleClient:
        is_connected = True

        def __init__(self) -> None:
            self.writes: list[tuple[str, bytes, bool]] = []

        async def write_gatt_char(self, uuid: str, data: bytes, response: bool) -> None:
            self.writes.append((uuid, bytes(data), response))

    async def scenario() -> list[tuple[str, bytes, bool]]:
        raw = FakeBleClient()
        client = PybricksHubClient()
        client._client = raw
        await client.drive(-LEGO_POWER, LEGO_POWER)
        return raw.writes

    assert asyncio.run(scenario()) == [
        (
            PYBRICKS_COMMAND_EVENT_CHAR_UUID,
            bytes((COMMAND_WRITE_STDIN,)) + encode_drive(-LEGO_POWER, LEGO_POWER),
            True,
        )
    ]
