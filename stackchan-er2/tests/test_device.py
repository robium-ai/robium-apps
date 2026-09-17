from __future__ import annotations

import json
import threading

import pytest

from stackchan_er2.audio import FakeTTS
from stackchan_er2.config import ANIMATION_NAMES, SAMPLE_RATE
from stackchan_er2.device import DeviceError, FakeStackChan, GuardedActions, SerialStackChan
from stackchan_er2.lego import FakeLegoRobot


class ScriptedSerial:
    def __init__(self, responses: list[dict], binary: bytes = b"") -> None:
        self.responses = [b"@stackchan " + json.dumps(item).encode() + b"\n" for item in responses]
        self.binary = bytearray(binary)
        self.writes: list[bytes] = []

    def write(self, data: bytes) -> int:
        self.writes.append(data)
        return len(data)

    def flush(self) -> None:
        pass

    def readline(self) -> bytes:
        return self.responses.pop(0)

    def read(self, size: int) -> bytes:
        chunk = bytes(self.binary[:size])
        del self.binary[:size]
        return chunk


def test_guard_executes_the_six_bounded_tools() -> None:
    device = FakeStackChan()
    lego = FakeLegoRobot()
    guard = GuardedActions(device, FakeTTS(), lego)

    assert (
        guard.execute("move_head", {"yaw": -20, "pitch": 55, "speed": 150})["status"] == "succeeded"
    )
    assert guard.execute("show_text", {"text": "Welcome"})["text"] == "Welcome"
    speech = guard.execute("speak", {"message": "Hello"})
    visual = guard.execute("look", {})
    animation = guard.execute("animate", {"animation": "nod_yes"})
    lego_motion = guard.execute("drive_lego", {"direction": "left"})

    assert speech["status"] == "succeeded"
    assert speech["sample_rate"] == SAMPLE_RATE
    assert visual["mime_type"] == "image/jpeg"
    assert visual["_image"] == b"\xff\xd8\xff\xd9"
    assert animation["animation"] == "nod_yes"
    assert lego_motion["direction"] == "left"
    assert lego_motion["stopped"] is True
    assert [name for name, _ in device.events] == [
        "move_head",
        "show_text",
        "show_text",
        "speak_pcm",
        "capture_image",
        "animate",
    ]


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("move_head", {"yaw": 90, "pitch": 45, "speed": 150}),
        ("move_head", {"yaw": 0, "pitch": 0, "speed": 150}),
        ("show_text", {"text": ""}),
        ("speak", {"message": "x" * 241}),
        ("animate", {"animation": "dance"}),
        ("drive_lego", {"direction": "spin"}),
        ("raw_motor", {}),
    ],
)
def test_guard_rejects_unsafe_or_unknown_actions(name: str, arguments: dict) -> None:
    guard = GuardedActions(FakeStackChan(), FakeTTS())
    with pytest.raises(DeviceError):
        guard.execute(name, arguments)


def test_fake_recording_has_exact_duration() -> None:
    device = FakeStackChan()
    pcm = device.record_audio(1.25)
    assert len(pcm) == int(SAMPLE_RATE * 1.25) * 2
    chunk = device.record_audio_chunk(0.25)
    assert len(chunk) == int(SAMPLE_RATE * 0.25) * 2
    assert device.stop_listening()["status"] == "succeeded"


def test_all_named_animations_are_supported() -> None:
    guard = GuardedActions(FakeStackChan(), FakeTTS())
    results = [guard.execute("animate", {"animation": name}) for name in ANIMATION_NAMES]

    assert [result["animation"] for result in results] == list(ANIMATION_NAMES)
    assert results[-2]["yaw"] == 180
    assert results[-1]["yaw"] == 0


def test_lego_tool_requires_a_connected_controller() -> None:
    guard = GuardedActions(FakeStackChan(), FakeTTS())
    with pytest.raises(DeviceError, match="disabled or not connected"):
        guard.execute("drive_lego", {"direction": "forward"})


def test_speech_waits_for_device_ready_before_sending_pcm() -> None:
    transport = ScriptedSerial(
        [
            {"id": 7, "status": "ready"},
            {"id": 7, "status": "succeeded", "audio_bytes": 4},
        ]
    )
    device = object.__new__(SerialStackChan)
    device._serial = transport
    device._lock = threading.Lock()
    device._next_id = 7

    result = device.speak_pcm(b"\x01\x00\x02\x00")

    assert result["status"] == "succeeded"
    assert len(transport.writes) == 2
    assert json.loads(transport.writes[0]) == {
        "id": 7,
        "command": "speak_pcm",
        "audio_bytes": 4,
        "sample_rate": SAMPLE_RATE,
    }
    assert transport.writes[1] == b"\x01\x00\x02\x00"


def test_camera_reads_the_exact_jpeg_payload() -> None:
    image = b"\xff\xd8camera\xff\xd9"
    transport = ScriptedSerial(
        [{"id": 9, "status": "succeeded", "image_bytes": len(image)}],
        binary=image,
    )
    device = object.__new__(SerialStackChan)
    device._serial = transport
    device._lock = threading.Lock()
    device._next_id = 9

    assert device.capture_image() == image
    assert json.loads(transport.writes[0]) == {"id": 9, "command": "capture_image"}


def test_named_animation_uses_the_serial_command() -> None:
    transport = ScriptedSerial(
        [{"id": 11, "status": "succeeded", "animation": "privacy", "pitch": 90}]
    )
    device = object.__new__(SerialStackChan)
    device._serial = transport
    device._lock = threading.Lock()
    device._next_id = 11

    assert device.animate("privacy")["pitch"] == 90
    assert json.loads(transport.writes[0]) == {
        "id": 11,
        "command": "animate",
        "animation": "privacy",
    }
