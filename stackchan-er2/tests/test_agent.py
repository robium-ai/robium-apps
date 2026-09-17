from __future__ import annotations

import asyncio
import base64
from types import SimpleNamespace

import pytest
from google.genai import types

from stackchan_er2.agent import StackChanAgent, function_declarations, iter_pcm_chunks, live_config
from stackchan_er2.audio import FakeTTS
from stackchan_er2.config import ANIMATION_NAMES, MODEL, PCM_CHUNK_BYTES
from stackchan_er2.device import FakeStackChan, GuardedActions


def test_only_five_semantic_tools_are_exposed() -> None:
    assert [tool["name"] for tool in function_declarations()] == [
        "move_head",
        "show_text",
        "speak",
        "look",
        "animate",
    ]
    assert function_declarations()[-1]["parameters"]["properties"]["animation"]["enum"] == list(
        ANIMATION_NAMES
    )
    assert MODEL == "gemini-robotics-er-2-streaming-preview"
    config = live_config()
    assert config.response_modalities == ["TEXT"]
    assert config.realtime_input_config.automatic_activity_detection.disabled is True

    continuous = live_config(continuous=True)
    assert continuous.realtime_input_config.automatic_activity_detection.disabled is False
    assert "Stack Chan" in continuous.system_instruction.parts[0].text
    assert "not to speak" in continuous.system_instruction.parts[0].text


def test_pcm_chunks_preserve_audio() -> None:
    pcm = b"\x01\x02" * 2001
    chunks = list(iter_pcm_chunks(pcm))
    assert b"".join(chunks) == pcm
    assert len(chunks[0]) == PCM_CHUNK_BYTES


def test_odd_pcm_is_rejected() -> None:
    with pytest.raises(ValueError):
        list(iter_pcm_chunks(b"\x00"))


def test_push_to_talk_sends_explicit_activity_boundaries() -> None:
    class RecordingSession:
        def __init__(self) -> None:
            self.messages: list[dict] = []

        async def send_realtime_input(self, **message: object) -> None:
            self.messages.append(message)

    session = RecordingSession()
    agent = object.__new__(StackChanAgent)
    asyncio.run(agent._send_audio(session, b"\x01\x00" * 2000))

    assert isinstance(session.messages[0]["activity_start"], types.ActivityStart)
    assert isinstance(session.messages[-1]["activity_end"], types.ActivityEnd)
    assert all("audio_stream_end" not in message for message in session.messages)
    audio = b"".join(message["audio"].data for message in session.messages[1:-1])
    assert audio == b"\x01\x00" * 2000


def test_continuous_loop_streams_device_chunks_without_manual_boundaries() -> None:
    class StreamComplete(Exception):
        pass

    class OneMessageSession:
        def __init__(self) -> None:
            self.message: dict | None = None

        async def send_realtime_input(self, **message: object) -> None:
            self.message = message
            raise StreamComplete

    async def run_one_chunk() -> tuple[FakeStackChan, OneMessageSession]:
        device = FakeStackChan()
        agent = object.__new__(StackChanAgent)
        agent.device = device
        session = OneMessageSession()
        listening = asyncio.Event()
        listening.set()
        with pytest.raises(StreamComplete):
            await agent._continuous_audio_loop(session, listening, chunk_seconds=0.25)
        return device, session

    device, session = asyncio.run(run_one_chunk())

    assert device.events[0][0] == "record_audio_chunk"
    assert session.message is not None
    assert set(session.message) == {"audio"}


def test_look_tool_attaches_image_to_its_function_response() -> None:
    class RecordingSession:
        def __init__(self) -> None:
            self.realtime: list[dict] = []
            self.responses: list[object] = []

        async def send_realtime_input(self, **message: object) -> None:
            self.realtime.append(message)

        async def send_tool_response(self, **message: object) -> None:
            self.responses.append(message)

    device = FakeStackChan()
    agent = object.__new__(StackChanAgent)
    agent.actions = GuardedActions(device, FakeTTS())
    session = RecordingSession()
    call = SimpleNamespace(name="look", args={}, id="look-1")

    successful = asyncio.run(agent._execute_tool_calls(session, [call]))

    assert successful == {"look"}
    assert [name for name, _ in device.events] == ["capture_image"]
    assert session.realtime == []
    function_response = session.responses[0]["function_responses"][0]
    assert function_response.response == {
        "status": "succeeded",
        "mime_type": "image/jpeg",
        "image_bytes": 4,
    }
    assert len(function_response.parts) == 1
    assert function_response.parts[0].inline_data.mime_type == "image/jpeg"
    encoded_image = function_response.parts[0].inline_data.data
    assert isinstance(encoded_image, str)
    assert base64.b64decode(encoded_image) == b"\xff\xd8\xff\xd9"


def test_display_only_tool_does_not_trigger_speech_fallback() -> None:
    class ScriptedSession:
        async def receive(self):
            yield SimpleNamespace(
                server_content=None,
                tool_call=SimpleNamespace(
                    function_calls=[
                        SimpleNamespace(
                            name="show_text",
                            args={"text": "Silent message"},
                            id="display-1",
                        )
                    ]
                ),
            )
            yield SimpleNamespace(
                server_content=SimpleNamespace(
                    model_turn=SimpleNamespace(parts=[SimpleNamespace(text="Done")]),
                    turn_complete=True,
                ),
                tool_call=None,
            )

        async def send_tool_response(self, **message: object) -> None:
            pass

    device = FakeStackChan()
    agent = object.__new__(StackChanAgent)
    agent.actions = GuardedActions(device, FakeTTS())

    asyncio.run(agent._receive_turn(ScriptedSession()))

    assert [name for name, _ in device.events] == ["show_text"]


def test_animation_only_tool_does_not_trigger_speech_fallback() -> None:
    class ScriptedSession:
        async def receive(self):
            yield SimpleNamespace(
                server_content=None,
                tool_call=SimpleNamespace(
                    function_calls=[
                        SimpleNamespace(
                            name="animate",
                            args={"animation": "nod_yes"},
                            id="animation-1",
                        )
                    ]
                ),
            )
            yield SimpleNamespace(
                server_content=SimpleNamespace(
                    model_turn=SimpleNamespace(parts=[SimpleNamespace(text="Done")]),
                    turn_complete=True,
                ),
                tool_call=None,
            )

        async def send_tool_response(self, **message: object) -> None:
            pass

    device = FakeStackChan()
    agent = object.__new__(StackChanAgent)
    agent.actions = GuardedActions(device, FakeTTS())

    asyncio.run(agent._receive_turn(ScriptedSession()))

    assert [name for name, _ in device.events] == ["animate"]
