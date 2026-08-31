"""The link to the mBot's bridge firmware, over USB or Bluetooth.

One command per line, one reply per command, with unsolicited "EV ..." lines
(the boot banner, the watchdog firing) filtered out of the reply stream rather
than mistaken for one.

Two transports carry that protocol, and the board cannot tell them apart. Over
USB a CH340 bridges to the ATmega's hardware UART. Over Bluetooth, Makeblock's
module bridges to the *same* UART - so the firmware needs no notion of which one
is in use, which is why the protocol was kept short and ASCII.

The Bluetooth module is BLE, not classic Bluetooth, and that distinction decides
the whole design here: macOS creates a `/dev/cu.*` serial port for classic SPP
devices and never for BLE ones. No amount of pairing will produce a port to open
with pyserial, so BLE needs a real GATT client. The module exposes the usual
HM-10 style transparent pair - notify on 0xFFE2, write on 0xFFE3 - which carries
bytes in both directions exactly as a serial port would.
"""

from __future__ import annotations

import queue
import threading
import time

import serial
from serial.tools import list_ports

from .config import CH340_VID

DEFAULT_BAUD = 115200

# Opening the serial port reboots the board, and optiboot waits before handing
# over to the sketch. Nothing we send before the banner is heard.
BOOT_TIMEOUT = 5.0

# Makeblock's BLE module, as a transparent UART.
BLE_SERVICE = "0000ffe1-0000-1000-8000-00805f9b34fb"
BLE_NOTIFY = "0000ffe2-0000-1000-8000-00805f9b34fb"
BLE_WRITE = "0000ffe3-0000-1000-8000-00805f9b34fb"
BLE_NAME_PREFIX = "Makeblock"

# Ports that are never the robot: macOS's own, and the incoming-BT listener.
_NEVER_THE_ROBOT = ("debug-console", "Bluetooth-Incoming-Port")


class LinkError(RuntimeError):
    pass


def find_port() -> str | None:
    """The mBot's serial port over USB, or None if it is not attached."""
    candidates = [p for p in list_ports.comports() if p.vid == CH340_VID]
    if not candidates:
        candidates = [
            p
            for p in list_ports.comports()
            if ("usbserial" in p.device or "usbmodem" in p.device)
            and not any(skip in p.device for skip in _NEVER_THE_ROBOT)
        ]
    return candidates[0].device if candidates else None


def candidate_ports() -> list[str]:
    """Every serial port that could plausibly be a robot, for `./app doctor`."""
    return [
        p.device
        for p in list_ports.comports()
        if not any(skip in p.device for skip in _NEVER_THE_ROBOT)
    ]


class _SerialTransport:
    """Bytes over USB."""

    # Opening the port pulls DTR, which resets the board.
    resets_on_connect = True

    def __init__(self, port: str, baud: int):
        try:
            self._serial = serial.Serial(port, baud, timeout=0.25)
        except serial.SerialException as exc:
            raise LinkError(f"Could not open {port}: {exc}") from exc

    def write_line(self, text: str) -> None:
        self._serial.write((text + "\n").encode("ascii"))
        self._serial.flush()

    def read_line(self, timeout: float) -> str:
        self._serial.timeout = timeout
        return self._serial.readline().decode("ascii", "replace").strip()

    def reset_input(self) -> None:
        self._serial.reset_input_buffer()

    def close(self) -> None:
        self._serial.close()


class _BleTransport:
    """Bytes over Makeblock's BLE module.

    bleak is asynchronous and the control loop is not, so the event loop runs on
    its own thread and every call here hands work to it and waits. That keeps
    the caller's timing simple - one command, one reply, no async in the control
    loop - at the cost of a thread hop per command, which is nothing next to a
    BLE connection interval.
    """

    # Nothing resets the board when a BLE client connects, so there is no boot
    # banner to wait for.
    resets_on_connect = False

    def __init__(self, address: str | None, connect_timeout: float = 20.0):
        import asyncio

        self._asyncio = asyncio
        self._lines: queue.Queue[str] = queue.Queue()
        self._partial = bytearray()
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._client = None
        self._submit(self._connect(address), timeout=connect_timeout)

    def _run_loop(self) -> None:
        self._asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _submit(self, coro, timeout: float):
        future = self._asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout=timeout)
        except Exception as exc:  # noqa: BLE001 - surfaced as one link error
            raise LinkError(str(exc)) from exc

    async def _connect(self, address: str | None) -> None:
        try:
            from bleak import BleakClient, BleakScanner
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise LinkError(
                "Bluetooth needs the 'bleak' package. Run './app build'."
            ) from exc

        if address:
            device = await BleakScanner.find_device_by_address(address, timeout=15.0)
        else:
            device = await BleakScanner.find_device_by_filter(
                lambda d, _: bool(d.name and d.name.startswith(BLE_NAME_PREFIX)),
                timeout=15.0,
            )
        if device is None:
            raise LinkError(
                "No Makeblock BLE module found. Check the mBot is powered on "
                "with the module attached."
            )

        self._client = BleakClient(device)
        await self._client.connect()
        await self._client.start_notify(BLE_NOTIFY, self._on_notify)

    def _on_notify(self, _sender: object, data: bytearray) -> None:
        # BLE delivers arbitrary chunks; the protocol is line-based, so
        # reassemble here rather than making every caller do it.
        self._partial.extend(data)
        while b"\n" in self._partial:
            raw, _, rest = self._partial.partition(b"\n")
            self._partial = bytearray(rest)
            line = raw.decode("ascii", "replace").strip()
            if line:
                self._lines.put(line)

    def write_line(self, text: str) -> None:
        payload = (text + "\n").encode("ascii")
        self._submit(
            self._client.write_gatt_char(BLE_WRITE, payload, response=False),
            timeout=5.0,
        )

    def read_line(self, timeout: float) -> str:
        try:
            return self._lines.get(timeout=timeout)
        except queue.Empty:
            return ""

    def reset_input(self) -> None:
        while True:
            try:
                self._lines.get_nowait()
            except queue.Empty:
                return

    def close(self) -> None:
        if self._client is not None:
            try:
                self._submit(self._client.disconnect(), timeout=5.0)
            except LinkError:
                pass
            self._client = None
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=2.0)


class MBotLink:
    """A connected mBot. Use as a context manager so the wheels always stop."""

    def __init__(
        self,
        port: str | None = None,
        watchdog_ms: int = 400,
        baud: int = DEFAULT_BAUD,
    ):
        self.requested_port = port
        self.baud = baud
        self.watchdog_ms = watchdog_ms
        self.banner = ""
        self._transport = None

        # "ble" alone discovers the module; "ble:<address>" names one, which
        # matters as soon as there are two robots in the room.
        if port and port.lower().startswith("ble"):
            self.port = port
            self._ble_address = port.split(":", 1)[1] if ":" in port else None
            self._use_ble = True
        else:
            self.port = port or find_port()
            self._ble_address = None
            self._use_ble = False
            if self.port is None:
                if port is not None:
                    raise LinkError(f"No such port: {port}")
                # Nothing on USB and no port was asked for. The robot is very
                # likely on Bluetooth, so try that rather than stopping - the
                # alternative is failing beside a robot that is powered on.
                print("No USB mBot found; trying Bluetooth. "
                      "(--port /dev/... or --port ble to be explicit.)")
                self.port = "ble"
                self._use_ble = True

    def __enter__(self) -> "MBotLink":
        self.connect()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def connect(self) -> None:
        if self._use_ble:
            self._transport = _BleTransport(self._ble_address)
        else:
            self._transport = _SerialTransport(self.port, self.baud)

        self.banner = self._await_banner()
        self.command(f"W {self.watchdog_ms}")
        self.stop()

    def _await_banner(self) -> str:
        """Identify the firmware, waiting for its boot banner where there is one."""
        if self._transport.resets_on_connect:
            deadline = time.monotonic() + BOOT_TIMEOUT
            while time.monotonic() < deadline:
                if (line := self._transport.read_line(0.25)).startswith("EV READY"):
                    return line
        # Either the transport does not reset the board, or the banner was
        # missed. Asking settles whether the firmware is there at all.
        try:
            return self.command("V")
        except LinkError as exc:
            where = "over Bluetooth" if self._use_ble else f"on {self.port}"
            raise LinkError(
                f"No response from the board {where}. "
                "Is the bridge firmware flashed? Run './app flash'."
            ) from exc

    def command(self, text: str, retries: int = 2) -> str:
        """Send one command and return its reply, skipping anything else.

        Three things can arrive that are not the answer, and all three are
        filtered here rather than left for callers to trip over: unsolicited
        "EV" events, and - because the control loop streams motor commands
        without reading their acknowledgements - stale "OK M" lines still in
        flight. Draining before writing is not enough on Bluetooth, where a
        notification sent before the drain can be delivered after it, so the
        reply is matched on its verb instead of merely being the next line.
        """
        if self._transport is None:
            raise LinkError("Not connected.")

        verb = text.strip()[:1]

        for _ in range(retries + 1):
            self._transport.reset_input()
            self._transport.write_line(text)

            deadline = time.monotonic() + 1.0
            while time.monotonic() < deadline:
                line = self._transport.read_line(0.25)
                if not line:
                    break
                if line.startswith("EV "):
                    continue  # a boot banner or watchdog notice, not our reply
                if line.startswith("ERR"):
                    raise LinkError(f"{text!r} rejected: {line}")
                if line.startswith("OK ") and line[3:4] != verb:
                    continue  # an acknowledgement for some earlier command
                return line
        raise LinkError(f"No reply to {text!r}")

    # -- the small vocabulary the rest of the app uses ---------------------

    def drive_pwm(self, m1: int, m2: int) -> None:
        """Send a motor command and wait for the board to acknowledge it."""
        self.command(f"M {int(m1)} {int(m2)}")

    def stream_pwm(self, m1: int, m2: int) -> None:
        """Send a motor command without waiting for the acknowledgement.

        This is what the control loop uses, and over Bluetooth it is the
        difference between working and not: a confirmed round trip measures
        ~60 ms on the BLE module, which is longer than the 50 ms control period
        at 20 Hz, so waiting would force the loop below its own rate.

        Dropping the acknowledgement is safe precisely because of the two
        decisions above it. The loop re-sends a command every single tick, so a
        lost one is corrected 50 ms later rather than persisting; and the board
        stops itself if it hears nothing at all, so silence can never be
        mistaken for "keep going". Commands that configure or interrogate the
        board still wait, because those happen once and their answers matter.
        """
        # Drop the acknowledgements nobody is reading, so they cannot pile up
        # and be mistaken for the reply to a later command.
        self._transport.reset_input()
        self._transport.write_line(f"M {int(m1)} {int(m2)}")

    def stop(self) -> None:
        self.command("S")

    def ping(self) -> str:
        return self.command("P")

    def version(self) -> str:
        return self.command("V")

    def telemetry(self) -> dict[str, int]:
        _, _, m1, m2, age, uptime = self.command("T").split()
        return {
            "m1": int(m1),
            "m2": int(m2),
            "since_command_ms": int(age),
            "uptime_ms": int(uptime),
        }

    def beep(self, hz: int = 880, ms: int = 120) -> None:
        self.command(f"Z {hz} {ms}")

    def close(self) -> None:
        if self._transport is None:
            return
        try:
            self.stop()
        except (LinkError, serial.SerialException):
            pass  # closing is not the moment to care why a stop failed
        finally:
            self._transport.close()
            self._transport = None
