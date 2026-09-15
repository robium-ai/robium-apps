"""Bluetooth link to a LEGO hub running the bundled Pybricks bridge."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any

from .protocol import EXIT, PING, PONG_LINE, READY_LINE, LineDecoder, encode_drive

# Official Pybricks GATT service and command/event characteristic.
PYBRICKS_SERVICE_UUID = "c5f50001-8280-46da-89f4-6d8051e4aeef"
PYBRICKS_COMMAND_EVENT_CHAR_UUID = "c5f50002-8280-46da-89f4-6d8051e4aeef"

COMMAND_START_USER_PROGRAM = 0x01
COMMAND_WRITE_STDIN = 0x06
EVENT_WRITE_STDOUT = 0x01

DEFAULT_SCAN_TIMEOUT = 10.0
DEFAULT_START_TIMEOUT = 8.0


class LinkError(RuntimeError):
    """Actionable Bluetooth or hub-program failure."""


@dataclass(frozen=True)
class HubCandidate:
    name: str
    address: str
    device: Any = field(compare=False, repr=False)


def choose_candidate(
    candidates: list[HubCandidate], hub_name: str | None = None
) -> HubCandidate:
    """Choose exactly one hub, requiring a name when discovery is ambiguous."""
    if hub_name:
        matches = [
            candidate
            for candidate in candidates
            if candidate.name.casefold() == hub_name.casefold()
        ]
        if not matches:
            found = ", ".join(sorted(candidate.name for candidate in candidates)) or "none"
            raise LinkError(f"No Pybricks hub named {hub_name!r} found (found: {found}).")
        if len(matches) > 1:
            raise LinkError(f"More than one advertising hub is named {hub_name!r}.")
        return matches[0]

    if not candidates:
        raise LinkError(
            "No advertising Pybricks hub found. Turn the hub on, disconnect "
            "Pybricks Code, and do not pair it in the computer's Bluetooth settings."
        )
    if len(candidates) > 1:
        names = ", ".join(sorted(candidate.name for candidate in candidates))
        raise LinkError(
            f"More than one Pybricks hub found ({names}). Re-run with --hub-name NAME."
        )
    return candidates[0]


async def scan_hubs(timeout: float = DEFAULT_SCAN_TIMEOUT) -> list[HubCandidate]:
    """Return nearby hubs advertising the Pybricks service."""
    try:
        from bleak import BleakScanner
        from bleak.exc import BleakBluetoothNotAvailableError
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise LinkError("Bluetooth support is missing. Run './app build'.") from exc

    try:
        found = await BleakScanner.discover(
            timeout=timeout,
            return_adv=True,
            service_uuids=[PYBRICKS_SERVICE_UUID],
        )
    except BleakBluetoothNotAvailableError as exc:
        raise LinkError(f"Bluetooth is unavailable: {exc}") from exc
    except Exception as exc:
        raise LinkError(f"Bluetooth scan failed: {exc}") from exc

    candidates: dict[str, HubCandidate] = {}
    for device, advertisement in found.values():
        services = {uuid.casefold() for uuid in advertisement.service_uuids}
        if PYBRICKS_SERVICE_UUID not in services:
            continue
        name = advertisement.local_name or device.name or "Unnamed Pybricks Hub"
        candidates[device.address] = HubCandidate(name, device.address, device)
    return sorted(candidates.values(), key=lambda candidate: (candidate.name, candidate.address))


class PybricksHubClient:
    """Async Pybricks client with program start and stdin/stdout framing."""

    def __init__(
        self,
        hub_name: str | None = None,
        scan_timeout: float = DEFAULT_SCAN_TIMEOUT,
        start_timeout: float = DEFAULT_START_TIMEOUT,
    ) -> None:
        self.hub_name = hub_name
        self.scan_timeout = scan_timeout
        self.start_timeout = start_timeout
        self.candidate: HubCandidate | None = None
        self._client: Any = None
        self._decoder = LineDecoder()
        self._ready = asyncio.Event()
        self._disconnected = asyncio.Event()
        self._lines: asyncio.Queue[str] = asyncio.Queue()

    @property
    def connected(self) -> bool:
        return bool(self._client is not None and self._client.is_connected)

    async def connect(self) -> HubCandidate:
        try:
            from bleak import BleakClient
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise LinkError("Bluetooth support is missing. Run './app build'.") from exc

        candidates = await scan_hubs(self.scan_timeout)
        self.candidate = choose_candidate(candidates, self.hub_name)
        self._client = BleakClient(
            self.candidate.device,
            disconnected_callback=self._on_disconnect,
        )
        try:
            await self._client.connect()
            await self._client.start_notify(
                PYBRICKS_COMMAND_EVENT_CHAR_UUID,
                self._on_notification,
            )
            # The bridge must already be saved in the hub, but the desktop app
            # starts it so the operator does not need a second button press.
            await self._write_command(bytes((COMMAND_START_USER_PROGRAM,)))
            await asyncio.wait_for(self._ready.wait(), timeout=self.start_timeout)
        except TimeoutError as exc:
            await self.disconnect(stop_program=False)
            raise LinkError(
                "The hub connected but did not report READY. Save hub/main.py "
                "to the hub and check that both configured motor ports are populated."
            ) from exc
        except Exception as exc:
            await self.disconnect(stop_program=False)
            if isinstance(exc, LinkError):
                raise
            raise LinkError(f"Could not start the hub bridge: {exc}") from exc
        return self.candidate

    def _on_disconnect(self, _client: Any) -> None:
        self._disconnected.set()

    def _on_notification(self, _sender: Any, data: bytearray) -> None:
        if not data or data[0] != EVENT_WRITE_STDOUT:
            return
        for line in self._decoder.feed(bytes(data[1:])):
            self._lines.put_nowait(line)
            if line == READY_LINE:
                self._ready.set()

    async def _write_command(self, payload: bytes) -> None:
        if not self.connected:
            raise LinkError("The hub is not connected.")
        await self._client.write_gatt_char(
            PYBRICKS_COMMAND_EVENT_CHAR_UUID,
            payload,
            response=True,
        )

    async def send_stdin(self, payload: bytes) -> None:
        await self._write_command(bytes((COMMAND_WRITE_STDIN,)) + payload)

    async def drive(self, left: int, right: int) -> None:
        await self.send_stdin(encode_drive(left, right))

    async def ping(self, timeout: float = 3.0) -> None:
        await self.send_stdin(PING)
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise LinkError("The hub did not answer PING with PONG.")
            try:
                line = await asyncio.wait_for(self._lines.get(), remaining)
            except TimeoutError as exc:
                raise LinkError("The hub did not answer PING with PONG.") from exc
            if line == PONG_LINE:
                return

    async def disconnect(self, *, stop_program: bool = True) -> None:
        client = self._client
        if client is None:
            return
        if client.is_connected and stop_program:
            with suppress(Exception):
                await self.send_stdin(encode_drive(0, 0))
                await self.send_stdin(EXIT)
                await asyncio.sleep(0.05)
        try:
            if client.is_connected:
                await client.disconnect()
        finally:
            self._client = None


async def hardware_smoke(
    hub_name: str | None = None,
    scan_timeout: float = DEFAULT_SCAN_TIMEOUT,
) -> HubCandidate:
    """Verify the real link and bridge without intentionally moving a motor."""
    client = PybricksHubClient(hub_name=hub_name, scan_timeout=scan_timeout)
    try:
        candidate = await client.connect()
        await client.drive(0, 0)
        await client.ping()
        return candidate
    finally:
        await client.disconnect()
