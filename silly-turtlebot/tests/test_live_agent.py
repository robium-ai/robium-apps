import asyncio
from types import SimpleNamespace

from silly_turtlebot.fake_robot import FakeRobot
from silly_turtlebot.guard import MissionGuard
from silly_turtlebot.live_agent import GeminiRoboticsLiveAgent, iter_pcm_chunks


def test_pcm_chunks_preserve_bytes_and_sample_alignment() -> None:
    data = bytes(range(200)) * 40

    chunks = list(iter_pcm_chunks(data))

    assert b"".join(chunks) == data
    assert all(len(chunk) % 2 == 0 for chunk in chunks)


class RecordingSession:
    def __init__(self) -> None:
        self.client_content: list[dict] = []
        self.realtime: list[dict] = []

    async def send_client_content(self, **kwargs) -> None:
        self.client_content.append(kwargs)

    async def send_realtime_input(self, **kwargs) -> None:
        self.realtime.append(kwargs)


class ReceivingSession(RecordingSession):
    def __init__(self, messages: list[SimpleNamespace]) -> None:
        super().__init__()
        self.messages = messages
        self.tool_responses = []

    async def receive(self):
        for message in self.messages:
            yield message

    async def send_tool_response(self, *, function_responses) -> None:
        self.tool_responses.extend(function_responses)


def test_audio_uses_realtime_chunks_and_explicit_stream_end(tmp_path) -> None:
    audio = tmp_path / "command.pcm"
    audio.write_bytes(b"\x01\x02" * 2000)
    session = RecordingSession()
    agent = GeminiRoboticsLiveAgent("fake-key", MissionGuard(FakeRobot()))

    asyncio.run(agent._send_input(session, None, None, audio))

    assert session.client_content == []
    assert session.realtime[-1] == {"audio_stream_end": True}


class CameraFake(FakeRobot):
    def look_around(self, quarter_turns: int):
        result = super().look_around(quarter_turns)
        self.frames = [b"jpeg-frame"]
        return result

    def consume_camera_frames(self):
        frames = getattr(self, "frames", [])
        self.frames = []
        return frames


def test_receive_loop_mediates_tools_and_forwards_fresh_camera() -> None:
    calls = [
        SimpleNamespace(name="look_around", args={"quarter_turns": 1}, id="call-1"),
        SimpleNamespace(name="publish_cmd_vel", args={"x": 1.0}, id="call-2"),
    ]
    messages = [
        SimpleNamespace(
            server_content=None,
            tool_call=SimpleNamespace(function_calls=calls),
        ),
        SimpleNamespace(
            server_content=SimpleNamespace(
                model_turn=SimpleNamespace(
                    parts=[SimpleNamespace(text="Navigation accepted.")]
                ),
                turn_complete=True,
            ),
            tool_call=None,
        ),
    ]
    session = ReceivingSession(messages)
    robot = CameraFake(location="living_room")
    agent = GeminiRoboticsLiveAgent("fake-key", MissionGuard(robot))

    text = asyncio.run(agent._receive_turn(session, timeout_s=1.0))

    assert text == ["Navigation accepted."]
    assert session.tool_responses[0].response["status"] == "succeeded"
    assert session.tool_responses[1].response["status"] == "rejected"
    assert session.realtime[0]["video"].data == b"jpeg-frame"
