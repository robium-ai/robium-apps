"""Exclusive BLE control for the LEGO Pybricks differential-drive robot."""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any

from .config import (
    LEGO_CONTROL_HZ,
    LEGO_DIRECTIONS,
    LEGO_MOVE_SECONDS,
    LEGO_POWER,
    LEGO_SCAN_TIMEOUT,
)

PYBRICKS_SERVICE_UUID = "c5f50001-8280-46da-89f4-6d8051e4aeef"
PYBRICKS_COMMAND_EVENT_CHAR_UUID = "c5f50002-8280-46da-89f4-6d8051e4aeef"

COMMAND_START_USER_PROGRAM = 0x01
COMMAND_WRITE_STDIN = 0x06
EVENT_WRITE_STDOUT = 0x01

DRIVE = b"D"
PING = b"P"
EXIT = b"X"
READY_LINE = "READY"
PONG_LINE = "PONG"
POWER_BIAS = 100


class LegoError(RuntimeError):
    """The LEGO hub is unavailable or rejected a bounded drive command."""


@dataclass(frozen=True)
class HubCandidate:
    name: str
    address: str
    device: Any = field(compare=False, repr=False)


@dataclass(frozen=True)
class LegoState:
    phase: str
    message: str
    hub_name: str | None = None


class LineDecoder:
    def __init__(self) -> None:
        self._partial = bytearray()

    def feed(self, payload: bytes) -> list[str]:
        self._partial.extend(payload)
        lines: list[str] = []
        while b"\n" in self._partial:
            raw, _, rest = self._partial.partition(b"\n")
            self._partial = bytearray(rest)
            line = raw.decode("ascii", "replace").strip()
            if line:
                lines.append(line)
        return lines


def encode_drive(left: int, right: int) -> bytes:
    values = (left, right)
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        raise TypeError("motor powers must be integers")
    if any(value < -100 or value > 100 for value in values):
        raise ValueError("motor power must be between -100 and 100")
    return DRIVE + bytes((left + POWER_BIAS, right + POWER_BIAS))


def wheels_for_direction(direction: str, power: int = LEGO_POWER) -> tuple[int, int]:
    """Map model-level directions to the robot's physically calibrated wheel powers."""
    if direction not in LEGO_DIRECTIONS:
        raise LegoError(f"unknown LEGO direction: {direction}")
    if not 1 <= power <= 60:
        raise ValueError("LEGO power must be between 1 and 60")
    # This robot's proven calibration has its throttle axis inverted while
    # retaining conventional differential steering.
    return {
        "forward": (-power, -power),
        "backward": (power, power),
        "left": (-power, power),
        "right": (power, -power),
        "stop": (0, 0),
    }[direction]


def choose_candidate(
    candidates: list[HubCandidate], hub_name: str | None = None
) -> HubCandidate:
    if hub_name:
        matches = [
            candidate
            for candidate in candidates
            if candidate.name.casefold() == hub_name.casefold()
        ]
        if not matches:
            found = ", ".join(sorted(candidate.name for candidate in candidates)) or "none"
            raise LegoError(f"No Pybricks hub named {hub_name!r} found (found: {found}).")
        if len(matches) > 1:
            raise LegoError(f"More than one advertising hub is named {hub_name!r}.")
        return matches[0]
    if not candidates:
        raise LegoError(
            "No advertising Pybricks hub found. Turn the hub on and disconnect other BLE clients."
        )
    if len(candidates) > 1:
        names = ", ".join(sorted(candidate.name for candidate in candidates))
        raise LegoError(f"More than one Pybricks hub found ({names}); pass --lego-hub-name.")
    return candidates[0]


async def scan_hubs(timeout: float = LEGO_SCAN_TIMEOUT) -> list[HubCandidate]:
    try:
        from bleak import BleakScanner
        from bleak.exc import BleakBluetoothNotAvailableError
    except ImportError as error:  # pragma: no cover - dependency guard
        raise LegoError("Bluetooth support is missing; run './app build'.") from error
    try:
        found = await BleakScanner.discover(
            timeout=timeout,
            return_adv=True,
            service_uuids=[PYBRICKS_SERVICE_UUID],
        )
    except BleakBluetoothNotAvailableError as error:
        raise LegoError(f"Bluetooth is unavailable: {error}") from error
    except Exception as error:
        raise LegoError(f"Bluetooth scan failed: {error}") from error

    candidates: dict[str, HubCandidate] = {}
    for device, advertisement in found.values():
        services = {uuid.casefold() for uuid in advertisement.service_uuids}
        if PYBRICKS_SERVICE_UUID not in services:
            continue
        name = advertisement.local_name or device.name or "Unnamed Pybricks Hub"
        candidates[device.address] = HubCandidate(name, device.address, device)
    return sorted(candidates.values(), key=lambda candidate: (candidate.name, candidate.address))


class PybricksHubClient:
    """BLE client for the saved watchdog bridge on the LEGO hub."""

    def __init__(
        self,
        hub_name: str | None = None,
        scan_timeout: float = LEGO_SCAN_TIMEOUT,
        start_timeout: float = 8.0,
    ) -> None:
        self.hub_name = hub_name
        self.scan_timeout = scan_timeout
        self.start_timeout = start_timeout
        self.candidate: HubCandidate | None = None
        self._client: Any = None
        self._decoder = LineDecoder()
        self._ready = asyncio.Event()
        self._lines: asyncio.Queue[str] = asyncio.Queue()

    @property
    def connected(self) -> bool:
        return bool(self._client is not None and self._client.is_connected)

    async def connect(self) -> HubCandidate:
        try:
            from bleak import BleakClient
        except ImportError as error:  # pragma: no cover - dependency guard
            raise LegoError("Bluetooth support is missing; run './app build'.") from error

        self.candidate = choose_candidate(await scan_hubs(self.scan_timeout), self.hub_name)
        self._client = BleakClient(self.candidate.device)
        try:
            await self._client.connect()
            await self._client.start_notify(
                PYBRICKS_COMMAND_EVENT_CHAR_UUID,
                self._on_notification,
            )
            await self._write_command(bytes((COMMAND_START_USER_PROGRAM,)))
            await asyncio.wait_for(self._ready.wait(), timeout=self.start_timeout)
        except TimeoutError as error:
            await self.disconnect(stop_program=False)
            raise LegoError(
                "The LEGO hub connected but its saved bridge did not report READY. "
                "Restart the hub and confirm the Stack Chan bridge program is saved."
            ) from error
        except Exception as error:
            await self.disconnect(stop_program=False)
            if isinstance(error, LegoError):
                raise
            raise LegoError(f"Could not start the LEGO bridge: {error}") from error
        return self.candidate

    def _on_notification(self, _sender: Any, data: bytearray) -> None:
        if not data or data[0] != EVENT_WRITE_STDOUT:
            return
        for line in self._decoder.feed(bytes(data[1:])):
            self._lines.put_nowait(line)
            if line == READY_LINE:
                self._ready.set()

    async def _write_command(self, payload: bytes) -> None:
        if not self.connected:
            raise LegoError("The LEGO hub is not connected.")
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
                raise LegoError("The LEGO hub did not answer PING with PONG.")
            try:
                line = await asyncio.wait_for(self._lines.get(), remaining)
            except TimeoutError as error:
                raise LegoError("The LEGO hub did not answer PING with PONG.") from error
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


class LegoDriveSession:
    """Persistent BLE worker with blocking, auto-stopping semantic commands."""

    def __init__(
        self,
        hub_name: str | None = None,
        scan_timeout: float = LEGO_SCAN_TIMEOUT,
        client_factory: Callable[..., PybricksHubClient] = PybricksHubClient,
    ) -> None:
        self.hub_name = hub_name
        self.scan_timeout = scan_timeout
        self._client_factory = client_factory
        self._condition = threading.Condition()
        self._command_lock = threading.Lock()
        self._desired_wheels = (0, 0)
        self._desired_revision = 0
        self._sent_revision = 0
        self._state = LegoState("idle", "LEGO session has not started")
        self._startup_complete = threading.Event()
        self._shutdown = threading.Event()
        self._thread: threading.Thread | None = None

    def state(self) -> LegoState:
        with self._condition:
            return self._state

    def _set_state(self, phase: str, message: str, hub_name: str | None = None) -> None:
        with self._condition:
            self._state = LegoState(phase, message, hub_name)
            self._condition.notify_all()
        if phase in {"ready", "error"}:
            self._startup_complete.set()

    def start(self, timeout: float | None = None) -> LegoState:
        if self._thread and self._thread.is_alive():
            return self.state()
        self._shutdown.clear()
        self._startup_complete.clear()
        self._thread = threading.Thread(target=self._thread_main, daemon=True)
        self._thread.start()
        wait_timeout = timeout if timeout is not None else self.scan_timeout + 10.0
        if not self._startup_complete.wait(wait_timeout):
            self.close()
            raise LegoError("Timed out starting the LEGO Bluetooth session.")
        state = self.state()
        if state.phase != "ready":
            self.close()
            raise LegoError(state.message)
        return state

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._run())
        except Exception as error:  # noqa: BLE001 - worker failure boundary
            self._set_state("error", f"LEGO Bluetooth worker failed: {error}")

    async def _run(self) -> None:
        client = self._client_factory(
            hub_name=self.hub_name,
            scan_timeout=self.scan_timeout,
        )
        try:
            self._set_state("scanning", "Scanning for the LEGO Pybricks hub")
            candidate = await client.connect()
            self._set_state("ready", "Connected to LEGO robot", candidate.name)
            period = 1.0 / LEGO_CONTROL_HZ
            while not self._shutdown.is_set():
                with self._condition:
                    wheels = self._desired_wheels
                    revision = self._desired_revision
                await client.drive(*wheels)
                with self._condition:
                    self._sent_revision = max(self._sent_revision, revision)
                    self._condition.notify_all()
                await asyncio.sleep(period)
        except LegoError as error:
            self._set_state("error", str(error))
        except Exception as error:  # noqa: BLE001 - surface backend failure
            self._set_state("error", f"LEGO Bluetooth connection failed: {error}")
        finally:
            await client.disconnect()
            if self.state().phase != "error":
                self._set_state("stopped", "LEGO robot stopped and disconnected")

    def _set_wheels(self, wheels: tuple[int, int]) -> int:
        with self._condition:
            self._desired_wheels = wheels
            self._desired_revision += 1
            return self._desired_revision

    def _wait_until_sent(self, revision: int, timeout: float = 2.0) -> None:
        deadline = time.monotonic() + timeout
        with self._condition:
            while self._sent_revision < revision:
                if self._state.phase == "error":
                    raise LegoError(self._state.message)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise LegoError("LEGO drive command was not transmitted before timeout.")
                self._condition.wait(remaining)

    def drive(self, direction: str) -> dict[str, Any]:
        wheels = wheels_for_direction(direction)
        with self._command_lock:
            state = self.state()
            if state.phase != "ready":
                raise LegoError(f"LEGO robot is not ready: {state.message}")
            revision = self._set_wheels(wheels)
            self._wait_until_sent(revision)
            duration = 0.0
            try:
                if direction != "stop":
                    duration = LEGO_MOVE_SECONDS
                    if self._shutdown.wait(duration):
                        raise LegoError("LEGO session stopped during the drive command.")
            finally:
                stop_revision = self._set_wheels((0, 0))
                self._wait_until_sent(stop_revision)
            return {
                "status": "succeeded",
                "direction": direction,
                "power": 0 if direction == "stop" else LEGO_POWER,
                "duration_seconds": duration,
                "stopped": True,
            }

    def close(self, timeout: float = 4.0) -> None:
        if self._thread and self._thread.is_alive() and self.state().phase == "ready":
            with suppress(LegoError):
                revision = self._set_wheels((0, 0))
                self._wait_until_sent(revision)
        self._shutdown.set()
        if self._thread:
            self._thread.join(timeout=timeout)


@dataclass
class FakeLegoRobot:
    events: list[dict[str, Any]] = field(default_factory=list)

    def drive(self, direction: str) -> dict[str, Any]:
        wheels = wheels_for_direction(direction)
        result = {
            "status": "succeeded",
            "direction": direction,
            "power": 0 if direction == "stop" else LEGO_POWER,
            "duration_seconds": 0.0 if direction == "stop" else LEGO_MOVE_SECONDS,
            "stopped": True,
            "wheels": wheels,
        }
        self.events.append(result.copy())
        return result


async def hardware_smoke(
    hub_name: str | None = None,
    scan_timeout: float = LEGO_SCAN_TIMEOUT,
) -> HubCandidate:
    """Verify the BLE bridge and watchdog path without moving the robot."""
    client = PybricksHubClient(hub_name=hub_name, scan_timeout=scan_timeout)
    try:
        candidate = await client.connect()
        await client.drive(0, 0)
        await client.ping()
        return candidate
    finally:
        await client.disconnect()
