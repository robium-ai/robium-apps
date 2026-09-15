from __future__ import annotations

import asyncio
from unittest.mock import Mock

import pytest

from lego_powered_up_teleop.link import (
    COMMAND_WRITE_STDIN,
    EVENT_WRITE_STDOUT,
    PYBRICKS_COMMAND_EVENT_CHAR_UUID,
    HubCandidate,
    LinkError,
    PybricksHubClient,
    choose_candidate,
)
from lego_powered_up_teleop.protocol import EXIT, PING, encode_drive


def _hub(name: str, address: str) -> HubCandidate:
    return HubCandidate(name, address, Mock())


def test_only_hub_is_selected_without_a_name() -> None:
    candidate = _hub("Pybricks Hub", "one")
    assert choose_candidate([candidate]) == candidate


def test_hub_name_selection_is_case_insensitive() -> None:
    wanted = _hub("Robot Red", "one")
    assert choose_candidate([wanted, _hub("Robot Blue", "two")], "robot red") == wanted


def test_multiple_hubs_require_an_explicit_name() -> None:
    with pytest.raises(LinkError, match="--hub-name"):
        choose_candidate([_hub("One", "one"), _hub("Two", "two")])


def test_missing_hub_error_has_setup_guidance() -> None:
    with pytest.raises(LinkError, match="Turn the hub on"):
        choose_candidate([])


class _FakeBleClient:
    def __init__(self) -> None:
        self.is_connected = True
        self.writes: list[tuple[str, bytes, bool]] = []

    async def write_gatt_char(self, uuid: str, data: bytes, response: bool) -> None:
        self.writes.append((uuid, bytes(data), response))

    async def disconnect(self) -> None:
        self.is_connected = False


def test_ping_reads_chunked_stdout_and_writes_stdin_command() -> None:
    async def scenario() -> None:
        client = PybricksHubClient()
        fake = _FakeBleClient()
        client._client = fake
        client._on_notification(None, bytearray((EVENT_WRITE_STDOUT,)) + b"REA")
        client._on_notification(None, bytearray((EVENT_WRITE_STDOUT,)) + b"DY\nPONG\n")

        await client.ping()

        assert client._ready.is_set()
        assert fake.writes == [
            (
                PYBRICKS_COMMAND_EVENT_CHAR_UUID,
                bytes((COMMAND_WRITE_STDIN,)) + PING,
                True,
            )
        ]

    asyncio.run(scenario())


def test_clean_disconnect_sends_zero_then_exits_program() -> None:
    async def scenario() -> None:
        client = PybricksHubClient()
        fake = _FakeBleClient()
        client._client = fake

        await client.disconnect()

        assert [write[1] for write in fake.writes] == [
            bytes((COMMAND_WRITE_STDIN,)) + encode_drive(0, 0),
            bytes((COMMAND_WRITE_STDIN,)) + EXIT,
        ]
        assert not fake.is_connected

    asyncio.run(scenario())
