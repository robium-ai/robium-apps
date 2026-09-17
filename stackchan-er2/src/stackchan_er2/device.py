"""Guarded newline-JSON plus binary-audio transport for STACK-CHAN."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Protocol, Self

import serial
from serial.tools import list_ports

from .config import (
    ANIMATION_NAMES,
    MAX_AUDIO_BYTES,
    MAX_IMAGE_BYTES,
    MAX_PITCH_DEG,
    MAX_RECORD_SECONDS,
    MAX_SPEECH_CHARS,
    MAX_SPEED,
    MAX_TEXT_CHARS,
    MAX_YAW_DEG,
    MIN_PITCH_DEG,
    MIN_SPEED,
    MIN_YAW_DEG,
    SAMPLE_RATE,
    SERIAL_BAUD,
    SERIAL_PID,
    SERIAL_VID,
)

PROTOCOL_PREFIX = b"@stackchan "


class DeviceError(RuntimeError):
    """The device rejected a request or the serial link failed."""


class StackChanDevice(Protocol):
    def status(self) -> dict[str, Any]: ...

    def move_head(self, yaw: int, pitch: int, speed: int) -> dict[str, Any]: ...

    def show_text(self, text: str) -> dict[str, Any]: ...

    def speak_pcm(self, pcm: bytes, sample_rate: int = SAMPLE_RATE) -> dict[str, Any]: ...

    def record_audio(self, seconds: float) -> bytes: ...

    def record_audio_chunk(self, seconds: float) -> bytes: ...

    def stop_listening(self) -> dict[str, Any]: ...

    def capture_image(self) -> bytes: ...

    def animate(self, animation: str) -> dict[str, Any]: ...


def discover_port(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    matches = [
        port.device
        for port in list_ports.comports()
        if port.vid == SERIAL_VID and port.pid == SERIAL_PID
    ]
    if not matches:
        raise DeviceError("STACK-CHAN was not found; connect its USB data cable or pass --port")
    if len(matches) > 1:
        raise DeviceError(f"multiple Espressif devices found: {', '.join(matches)}; pass --port")
    return matches[0]


class SerialStackChan:
    """Synchronous request/response client for the companion firmware."""

    def __init__(self, port: str | None = None, *, startup_timeout_s: float = 8.0):
        self.port = discover_port(port)
        self._serial = serial.Serial()
        self._serial.port = self.port
        self._serial.baudrate = SERIAL_BAUD
        self._serial.timeout = 0.2
        self._serial.write_timeout = 20
        self._serial.dtr = False
        self._serial.rts = False
        self._serial.open()
        self._lock = threading.Lock()
        self._next_id = 1
        self._wait_until_ready(startup_timeout_s)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self._serial.is_open:
            self._serial.close()

    def _wait_until_ready(self, timeout_s: float) -> None:
        deadline = time.monotonic() + timeout_s
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                self._serial.reset_input_buffer()
                result = self._request("ping", timeout_s=1.0)
                if result.get("firmware") == "stackchan-er2":
                    return
            except (DeviceError, serial.SerialException) as error:
                last_error = error
            time.sleep(0.25)
        detail = f": {last_error}" if last_error else ""
        raise DeviceError(
            f"{self.port} is present but the stackchan-er2 firmware did not answer{detail}"
        )

    def _read_response(self, request_id: int, deadline: float) -> dict[str, Any]:
        while time.monotonic() < deadline:
            line = self._serial.readline()
            if not line.startswith(PROTOCOL_PREFIX):
                continue
            try:
                response = json.loads(line[len(PROTOCOL_PREFIX) :])
            except json.JSONDecodeError:
                continue
            if response.get("id") != request_id:
                continue
            if response.get("status") == "error":
                raise DeviceError(str(response.get("error", "device rejected request")))
            return response
        raise DeviceError(f"timed out waiting for STACK-CHAN request {request_id}")

    def _read_exact(self, byte_count: int, deadline: float) -> bytes:
        payload = bytearray()
        while len(payload) < byte_count and time.monotonic() < deadline:
            payload.extend(self._serial.read(byte_count - len(payload)))
        if len(payload) != byte_count:
            raise DeviceError(f"expected {byte_count} audio bytes, received {len(payload)}")
        return bytes(payload)

    def _request(
        self,
        command: str,
        *,
        timeout_s: float = 10.0,
        **arguments: Any,
    ) -> dict[str, Any]:
        with self._lock:
            request_id = self._next_id
            self._next_id += 1
            message = {"id": request_id, "command": command, **arguments}
            encoded = json.dumps(message, separators=(",", ":"), ensure_ascii=False).encode()
            try:
                self._serial.write(encoded + b"\n")
                self._serial.flush()
            except serial.SerialException as error:
                raise DeviceError(f"serial write failed: {error}") from error
            deadline = time.monotonic() + timeout_s
            return self._read_response(request_id, deadline)

    def status(self) -> dict[str, Any]:
        return self._request("status")

    def move_head(self, yaw: int, pitch: int, speed: int) -> dict[str, Any]:
        return self._request("move_head", yaw=yaw, pitch=pitch, speed=speed, timeout_s=8)

    def show_text(self, text: str) -> dict[str, Any]:
        return self._request("show_text", text=text)

    def speak_pcm(self, pcm: bytes, sample_rate: int = SAMPLE_RATE) -> dict[str, Any]:
        if not pcm or len(pcm) % 2:
            raise ValueError("speech audio must contain signed 16-bit PCM samples")
        if len(pcm) > MAX_AUDIO_BYTES:
            raise ValueError(f"speech audio exceeds {MAX_AUDIO_BYTES} bytes")
        timeout = len(pcm) / (sample_rate * 2) + 25
        with self._lock:
            request_id = self._next_id
            self._next_id += 1
            message = {
                "id": request_id,
                "command": "speak_pcm",
                "audio_bytes": len(pcm),
                "sample_rate": sample_rate,
            }
            self._serial.write(json.dumps(message, separators=(",", ":")).encode() + b"\n")
            self._serial.flush()
            deadline = time.monotonic() + timeout
            ready = self._read_response(request_id, deadline)
            if ready.get("status") != "ready":
                raise DeviceError("STACK-CHAN did not request the speech payload")
            chunk_bytes = int(ready.get("chunk_bytes", 240))
            if not 1 <= chunk_bytes <= 240:
                raise DeviceError(f"invalid device audio chunk size: {chunk_bytes}")
            for offset in range(0, len(pcm), chunk_bytes):
                chunk = pcm[offset : offset + chunk_bytes]
                try:
                    written = self._serial.write(chunk)
                    self._serial.flush()
                except serial.SerialException as error:
                    raise DeviceError(f"serial audio write failed: {error}") from error
                if written != len(chunk):
                    raise DeviceError(f"serial audio write stopped at {written}/{len(chunk)} bytes")
                received = offset + len(chunk)
                if received < len(pcm):
                    progress = self._read_response(request_id, deadline)
                    if (
                        progress.get("status") != "continue"
                        or progress.get("received_bytes") != received
                    ):
                        raise DeviceError("STACK-CHAN speech transfer lost synchronization")
            return self._read_response(request_id, deadline)

    def _capture_audio(self, command: str, seconds: float, minimum_seconds: float) -> bytes:
        if not minimum_seconds <= seconds <= MAX_RECORD_SECONDS:
            raise ValueError(
                f"recording duration must be between {minimum_seconds} and {MAX_RECORD_SECONDS}s"
            )
        with self._lock:
            request_id = self._next_id
            self._next_id += 1
            message = {
                "id": request_id,
                "command": command,
                "duration_ms": round(seconds * 1000),
                "sample_rate": SAMPLE_RATE,
            }
            self._serial.write(json.dumps(message, separators=(",", ":")).encode() + b"\n")
            self._serial.flush()
            deadline = time.monotonic() + seconds + 15
            response = self._read_response(request_id, deadline)
            byte_count = int(response.get("audio_bytes", 0))
            if byte_count <= 0 or byte_count > MAX_AUDIO_BYTES:
                raise DeviceError(f"invalid recorded audio length: {byte_count}")
            return self._read_exact(byte_count, deadline)

    def record_audio(self, seconds: float) -> bytes:
        return self._capture_audio("record_audio", seconds, 0.25)

    def record_audio_chunk(self, seconds: float) -> bytes:
        return self._capture_audio("listen_chunk", seconds, 0.1)

    def stop_listening(self) -> dict[str, Any]:
        return self._request("stop_listening")

    def capture_image(self) -> bytes:
        with self._lock:
            request_id = self._next_id
            self._next_id += 1
            message = {"id": request_id, "command": "capture_image"}
            self._serial.write(json.dumps(message, separators=(",", ":")).encode() + b"\n")
            self._serial.flush()
            deadline = time.monotonic() + 20
            response = self._read_response(request_id, deadline)
            byte_count = int(response.get("image_bytes", 0))
            if not 4 <= byte_count <= MAX_IMAGE_BYTES:
                raise DeviceError(f"invalid captured image length: {byte_count}")
            image = self._read_exact(byte_count, deadline)
            if not image.startswith(b"\xff\xd8") or not image.endswith(b"\xff\xd9"):
                raise DeviceError("STACK-CHAN returned an invalid JPEG image")
            return image

    def animate(self, animation: str) -> dict[str, Any]:
        return self._request("animate", animation=animation, timeout_s=20)


@dataclass
class FakeStackChan:
    """Deterministic hardware-free adapter used by tests and the demo."""

    events: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    yaw: int = 0
    pitch: int = 45

    def status(self) -> dict[str, Any]:
        result = {"status": "succeeded", "yaw": self.yaw, "pitch": self.pitch}
        self.events.append(("status", result.copy()))
        return result

    def move_head(self, yaw: int, pitch: int, speed: int) -> dict[str, Any]:
        self.yaw, self.pitch = yaw, pitch
        result = {"status": "succeeded", "yaw": yaw, "pitch": pitch, "speed": speed}
        self.events.append(("move_head", result.copy()))
        return result

    def show_text(self, text: str) -> dict[str, Any]:
        result = {"status": "succeeded", "text": text}
        self.events.append(("show_text", result.copy()))
        return result

    def speak_pcm(self, pcm: bytes, sample_rate: int = SAMPLE_RATE) -> dict[str, Any]:
        result = {
            "status": "succeeded",
            "audio_bytes": len(pcm),
            "sample_rate": sample_rate,
        }
        self.events.append(("speak_pcm", result.copy()))
        return result

    def record_audio(self, seconds: float) -> bytes:
        pcm = b"\0\0" * int(SAMPLE_RATE * seconds)
        self.events.append(("record_audio", {"seconds": seconds, "audio_bytes": len(pcm)}))
        return pcm

    def record_audio_chunk(self, seconds: float) -> bytes:
        pcm = b"\0\0" * int(SAMPLE_RATE * seconds)
        self.events.append(("record_audio_chunk", {"seconds": seconds, "audio_bytes": len(pcm)}))
        return pcm

    def stop_listening(self) -> dict[str, Any]:
        result = {"status": "succeeded"}
        self.events.append(("stop_listening", result.copy()))
        return result

    def capture_image(self) -> bytes:
        image = b"\xff\xd8\xff\xd9"
        self.events.append(("capture_image", {"image_bytes": len(image)}))
        return image

    def animate(self, animation: str) -> dict[str, Any]:
        poses = {
            "nod_yes": (0, 45),
            "shake_no": (0, 45),
            "privacy": (0, 90),
            "turn_back": (180, 45),
            "look_straight": (0, 45),
        }
        if animation not in poses:
            raise DeviceError(f"unknown animation: {animation}")
        self.yaw, self.pitch = poses[animation]
        result = {
            "status": "succeeded",
            "animation": animation,
            "yaw": self.yaw,
            "pitch": self.pitch,
        }
        self.events.append(("animate", result.copy()))
        return result


class GuardedActions:
    """Validate every model-selected action before it reaches the device."""

    def __init__(self, device: StackChanDevice, tts: Any):
        self.device = device
        self.tts = tts

    @staticmethod
    def _bounded_int(name: str, value: Any, minimum: int, maximum: int) -> int:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise DeviceError(f"{name} must be a number")
        value = int(value)
        if not minimum <= value <= maximum:
            raise DeviceError(f"{name} must be between {minimum} and {maximum}")
        return value

    @staticmethod
    def _text(name: str, value: Any, maximum: int) -> str:
        if not isinstance(value, str) or not value.strip():
            raise DeviceError(f"{name} must be non-empty text")
        value = value.strip()
        if len(value) > maximum:
            raise DeviceError(f"{name} exceeds {maximum} characters")
        return value

    def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "move_head":
            yaw = self._bounded_int("yaw", arguments.get("yaw"), MIN_YAW_DEG, MAX_YAW_DEG)
            pitch = self._bounded_int("pitch", arguments.get("pitch"), MIN_PITCH_DEG, MAX_PITCH_DEG)
            speed = self._bounded_int("speed", arguments.get("speed", 150), MIN_SPEED, MAX_SPEED)
            return self.device.move_head(yaw, pitch, speed)
        if name == "show_text":
            text = self._text("text", arguments.get("text"), MAX_TEXT_CHARS)
            return self.device.show_text(text)
        if name == "speak":
            message = self._text("message", arguments.get("message"), MAX_SPEECH_CHARS)
            self.device.show_text(message)
            pcm = self.tts.synthesize(message)
            result = self.device.speak_pcm(pcm)
            return {**result, "message": message}
        if name == "look":
            image = self.device.capture_image()
            if len(image) > MAX_IMAGE_BYTES:
                raise DeviceError(f"captured image exceeds {MAX_IMAGE_BYTES} bytes")
            return {
                "status": "succeeded",
                "mime_type": "image/jpeg",
                "image_bytes": len(image),
                "_image": image,
            }
        if name == "animate":
            animation = arguments.get("animation")
            if not isinstance(animation, str) or animation not in ANIMATION_NAMES:
                allowed = ", ".join(ANIMATION_NAMES)
                raise DeviceError(f"animation must be one of: {allowed}")
            return self.device.animate(animation)
        raise DeviceError(f"tool is not allowed: {name}")
