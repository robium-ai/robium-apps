"""Threaded control session that keeps Bluetooth off the Pygame event loop."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from dataclasses import dataclass

from .link import LinkError, PybricksHubClient
from .protocol import mix

CONTROL_HZ = 10.0


@dataclass(frozen=True)
class SessionState:
    phase: str
    message: str
    hub_name: str | None = None

    @property
    def is_error(self) -> bool:
        return self.phase == "error"

    @property
    def is_ready(self) -> bool:
        return self.phase == "ready"


class DriveSession:
    """Own a BLE worker and expose non-blocking controls to the UI thread."""

    def __init__(
        self,
        hub_name: str | None = None,
        scan_timeout: float = 10.0,
        client_factory: Callable[..., PybricksHubClient] = PybricksHubClient,
    ) -> None:
        self.hub_name = hub_name
        self.scan_timeout = scan_timeout
        self._client_factory = client_factory
        self._lock = threading.Lock()
        self._action = (0.0, 0.0)
        self._speed = 35
        self._state = SessionState("idle", "Ready to scan")
        self._shutdown = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._shutdown.clear()
        self._thread = threading.Thread(target=self._thread_main, daemon=True)
        self._thread.start()

    def set_action(self, throttle: float, steer: float, speed: int) -> None:
        with self._lock:
            self._action = (float(throttle), float(steer))
            self._speed = int(speed)

    def desired_wheels(self) -> tuple[int, int]:
        with self._lock:
            throttle, steer = self._action
            speed = self._speed
        return mix(throttle, steer, speed)

    def state(self) -> SessionState:
        with self._lock:
            return self._state

    def _set_state(self, phase: str, message: str, hub_name: str | None = None) -> None:
        with self._lock:
            self._state = SessionState(phase, message, hub_name)

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._run())
        except Exception as exc:  # noqa: BLE001 - last-resort worker boundary
            self._set_state("error", f"Bluetooth worker failed: {exc}")

    async def _run(self) -> None:
        client = self._client_factory(
            hub_name=self.hub_name,
            scan_timeout=self.scan_timeout,
        )
        try:
            self._set_state("scanning", "Scanning for a powered-on Pybricks hub…")
            candidate = await client.connect()
            self._set_state("ready", "Connected — hold a direction to drive", candidate.name)
            period = 1.0 / CONTROL_HZ
            while not self._shutdown.is_set():
                left, right = self.desired_wheels()
                await client.drive(left, right)
                await asyncio.sleep(period)
        except LinkError as exc:
            self._set_state("error", str(exc))
        except Exception as exc:  # noqa: BLE001 - surface BLE backend failures
            self._set_state("error", f"Bluetooth connection failed: {exc}")
        finally:
            # The first zero is best effort over BLE. EXIT makes the hub-side
            # finally block brake again. Its independent watchdog covers a lost
            # link where neither message can arrive.
            await client.disconnect()
            if self.state().phase != "error":
                self._set_state("stopped", "Disconnected safely")

    def close(self, timeout: float = 3.0) -> None:
        self.set_action(0.0, 0.0, self._speed)
        self._shutdown.set()
        if self._thread:
            self._thread.join(timeout=timeout)
