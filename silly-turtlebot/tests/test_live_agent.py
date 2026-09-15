import asyncio
import threading
from types import SimpleNamespace

from silly_turtlebot.fake_robot import FakeRobot
from silly_turtlebot.guard import MissionGuard
from silly_turtlebot.live_agent import (
    GeminiRoboticsLiveAgent,
    PersistentGeminiSession,
    compact_heartbeat_state,
    compact_robot_state,
    iter_pcm_chunks,
)


def test_pcm_chunks_preserve_bytes_and_sample_alignment() -> None:
    data = bytes(range(200)) * 40

    chunks = list(iter_pcm_chunks(data))

    assert b"".join(chunks) == data
    assert all(len(chunk) % 2 == 0 for chunk in chunks)


def test_model_state_summaries_omit_static_heartbeat_metadata() -> None:
    state = {
        "status": "ok",
        "navigate_to_pose": True,
        "is_docked": False,
        "locations": [],
        "motion": {"state": "moving", "action": "spin", "elapsed_s": 1.2},
        "odometry": {
            "frame_id": "odom",
            "x": -0.722,
            "y": -0.221,
            "yaw_rad": 1.987,
            "linear_mps": 0.0,
            "angular_rad_s": 0.4,
        },
        "cameras": {
            "primary": {
                "topic": "http://camera",
                "fresh": True,
                "width": 640,
                "height": 360,
                "horizontal_fov_deg": 64.81,
                "vertical_fov_deg": 39.3,
                "mount_yaw_deg": 0,
                "mount_pitch_deg": 0,
            },
            "secondary": {
                "topic": "",
                "fresh": False,
                "width": 640,
                "height": 360,
                "horizontal_fov_deg": 69,
                "vertical_fov_deg": 42,
            },
        },
        "speech": {"model": "Kokoro", "voice": "am_puck"},
    }
    active_tool = {
        "call_id": "call-1",
        "name": "rotate_by",
        "elapsed_s": 1.25,
    }

    heartbeat = compact_heartbeat_state(state, active_tool)
    assert heartbeat == {
        "task": "active",
        "tool": {"name": "rotate_by", "state": "running", "elapsed_s": 1.25},
        "motion": {
            "state": "moving",
            "action": "spin",
            "elapsed_s": 1.2,
            "linear_mps": 0.0,
            "angular_rad_s": 0.4,
        },
        "is_docked": False,
    }
    assert "call_id" not in str(heartbeat)
    assert "speech" not in heartbeat
    assert "cameras" not in heartbeat
    assert "odometry" not in heartbeat

    mission_start = compact_robot_state(state, include_camera_geometry=True)
    assert mission_start["camera_geometry"] == {
        "primary": {
            "width": 640,
            "height": 360,
            "horizontal_fov_deg": 64.81,
            "vertical_fov_deg": 39.3,
            "mount_yaw_deg": 0,
            "mount_pitch_deg": 0,
        }
    }
    assert "speech" not in mission_start
    assert "navigate_to_pose" not in mission_start


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


def live_message(*, text: str | None = None, turn_complete: bool = False):
    model_turn = (
        SimpleNamespace(parts=[SimpleNamespace(text=text)]) if text else None
    )
    return SimpleNamespace(
        go_away=None,
        server_content=SimpleNamespace(
            model_turn=model_turn,
            turn_complete=turn_complete,
            interrupted=False,
        ),
        tool_call=None,
        tool_call_cancellation=None,
    )


def live_tool_message(name: str, call_id: str, args: dict):
    return SimpleNamespace(
        go_away=None,
        server_content=None,
        tool_call=SimpleNamespace(
            function_calls=[SimpleNamespace(name=name, args=args, id=call_id)]
        ),
        tool_call_cancellation=None,
    )


class PersistentFakeSession(RecordingSession):
    def __init__(self) -> None:
        super().__init__()
        self.incoming: asyncio.Queue[SimpleNamespace] = asyncio.Queue()
        self.tool_responses = []

    async def send_client_content(self, **kwargs) -> None:
        await super().send_client_content(**kwargs)
        if len(self.client_content) == 1:
            # A rapid update can be coalesced into the current Live turn rather
            # than producing one turn_complete message per submitted input.
            return
        text = kwargs["turns"].parts[0].text
        self.incoming.put_nowait(live_message(text=f"accepted: {text}"))
        self.incoming.put_nowait(
            live_tool_message(
                "complete_task",
                f"complete-{len(self.client_content)}",
                {"summary": "instruction complete"},
            )
        )

    async def receive(self):
        yield await self.incoming.get()

    async def send_tool_response(self, *, function_responses) -> None:
        self.tool_responses.extend(function_responses)
        self.incoming.put_nowait(live_message(turn_complete=True))


class FakeConnect:
    def __init__(self, live) -> None:
        self.live = live

    async def __aenter__(self):
        self.live.connection_count += 1
        return self.live.session

    async def __aexit__(self, *_args):
        return None


class FakeLive:
    def __init__(self, session) -> None:
        self.session = session
        self.connection_count = 0

    def connect(self, **_kwargs):
        return FakeConnect(self)


async def wait_until(predicate, timeout_s: float = 1.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_s
    while not predicate() and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.01)
    assert predicate()


def test_persistent_session_reuses_one_connection_for_two_instructions() -> None:
    async def scenario() -> None:
        model_session = PersistentFakeSession()
        live = FakeLive(model_session)
        client = SimpleNamespace(aio=SimpleNamespace(live=live))
        events: list[tuple[str, str, dict]] = []
        agent = PersistentGeminiSession(
            "fake-key",
            MissionGuard(FakeRobot()),
            lambda mission_id, kind, payload: events.append(
                (mission_id, kind, payload)
            ),
            client=client,
            camera_interval_s=0,
            heartbeat_idle_s=0,
        )

        await agent.submit_instruction("mission-1", "look once")
        await agent.submit_instruction("mission-1", "look twice", update=True)
        await wait_until(
            lambda: ("mission-1", "mission.completed")
            in [(mission_id, kind) for mission_id, kind, _ in events]
        )
        await agent.submit_instruction("mission-2", "look a third time")
        await wait_until(
            lambda: ("mission-2", "mission.completed")
            in [(mission_id, kind) for mission_id, kind, _ in events]
        )

        assert live.connection_count == 1
        assert [
            call["turns"].parts[-1].text.splitlines()[0]
            for call in model_session.client_content
        ] == [
            "Operator instruction: look once",
            "Operator instruction: look twice",
            "Operator instruction: look a third time",
        ]
        submitted = [
            call["turns"].parts[-1].text for call in model_session.client_content
        ]
        assert "camera_geometry" in submitted[0]
        assert "camera_geometry" not in submitted[1]
        assert "camera_geometry" in submitted[2]
        for mission_id in ("mission-1", "mission-2"):
            kinds = [kind for event_mission, kind, _ in events if event_mission == mission_id]
            assert kinds.index("input.sent") < kinds.index("model.text.delta")
            assert kinds.index("model.text.delta") < kinds.index("mission.completed")
        await agent.shutdown()

    asyncio.run(scenario())


class CountingRobot(FakeRobot):
    def __init__(self) -> None:
        super().__init__()
        self.look_calls = 0
        self.stop_calls = 0

    def look_around(self, quarter_turns: int):
        self.look_calls += 1
        return super().look_around(quarter_turns)

    def stop(self, reason: str):
        self.stop_calls += 1
        return super().stop(reason)


class FailingConnect:
    async def __aenter__(self):
        raise ConnectionError("test disconnect")

    async def __aexit__(self, *_args):
        return None


class FailingLive:
    def connect(self, **_kwargs):
        return FailingConnect()


def test_connection_loss_stops_robot_and_duplicate_call_is_not_replayed() -> None:
    async def scenario() -> None:
        robot = CountingRobot()
        events: list[tuple[str, str, dict]] = []
        client = SimpleNamespace(aio=SimpleNamespace(live=FailingLive()))
        agent = PersistentGeminiSession(
            "fake-key",
            MissionGuard(robot),
            lambda mission_id, kind, payload: events.append(
                (mission_id, kind, payload)
            ),
            client=client,
            camera_interval_s=0,
            heartbeat_idle_s=0,
            max_reconnect_attempts=0,
        )

        await agent.submit_instruction("lost-mission", "look around")
        await wait_until(
            lambda: any(kind == "mission.failed" for _, kind, _ in events)
        )
        assert robot.stop_calls == 1
        assert agent._writes is not None and agent._writes.empty()

        agent._active_mission_id = "dedupe-mission"
        call = SimpleNamespace(
            name="look_around",
            args={"quarter_turns": 1},
            id="duplicate-call",
        )
        await agent._handle_tool_calls(None, [call])
        await agent._handle_tool_calls(None, [call])
        await wait_until(lambda: robot.look_calls == 1)
        assert robot.look_calls == 1
        await agent._handle_tool_calls(None, [call])
        assert sum(
            response.id == "duplicate-call"
            for item in list(agent._writes._queue)
            if item.kind == "tool_response"
            for response in item.payload["responses"]
        ) == 1

        await agent.abort_active("operator stop")
        assert robot.stop_calls == 2
        assert agent._writes.empty()
        late_call = SimpleNamespace(
            name="look_around",
            args={"quarter_turns": 1},
            id="late-call",
        )
        await agent._handle_tool_calls(None, [late_call])
        assert robot.look_calls == 1
        await agent.shutdown()

    asyncio.run(scenario())


class BlockingRobot(CountingRobot):
    def __init__(self) -> None:
        super().__init__()
        self.action_started = threading.Event()
        self.action_release = threading.Event()

    def look_around(self, quarter_turns: int):
        self.look_calls += 1
        self.action_started.set()
        self.action_release.wait(timeout=2.0)
        return FakeRobot.look_around(self, quarter_turns)

    def stop(self, reason: str):
        self.action_release.set()
        return super().stop(reason)


def test_long_running_tool_streams_images_not_heartbeats_and_rejects_conflict() -> None:
    async def scenario() -> None:
        robot = BlockingRobot()
        events: list[tuple[str, str, dict]] = []
        agent = PersistentGeminiSession(
            "fake-key",
            MissionGuard(robot),
            lambda mission_id, kind, payload: events.append(
                (mission_id, kind, payload)
            ),
            client=SimpleNamespace(),
            camera_interval_s=1.0,
            heartbeat_idle_s=0.02,
        )
        session = PersistentFakeSession()
        agent._active_mission_id = "mission-running"
        agent._connection_state = "ready"
        agent._pending_turns = 1
        writer = asyncio.create_task(agent._writer(session))
        heartbeat = asyncio.create_task(agent._heartbeat_loop())
        first = SimpleNamespace(
            name="look_around", args={"quarter_turns": 1}, id="call-running"
        )
        conflict = SimpleNamespace(
            name="rotate_by", args={"angle_deg": 15}, id="call-conflict"
        )

        await agent._handle_tool_calls(session, [first])
        await asyncio.to_thread(robot.action_started.wait, 1.0)
        await agent._handle_tool_calls(session, [conflict])
        await wait_until(
            lambda: any(response.id == "call-conflict" for response in session.tool_responses)
        )
        await agent._queue_write(
            1,
            "camera",
            "mission-running",
            b"frame-during-tool",
        )
        await wait_until(
            lambda: any(
                item.get("video") is not None for item in session.realtime
            )
        )
        await asyncio.sleep(0.08)
        assert not any(item.get("text") for item in session.realtime)
        assert any(kind == "tool.progress" for _, kind, _ in events)
        assert robot.look_calls == 1
        rejected = next(
            response for response in session.tool_responses if response.id == "call-conflict"
        )
        assert rejected.response["status"] == "rejected"
        assert rejected.response["active_call_id"] == "call-running"

        robot.action_release.set()
        await wait_until(
            lambda: any(response.id == "call-running" for response in session.tool_responses)
        )
        original = next(
            response for response in session.tool_responses if response.id == "call-running"
        )
        assert original.response["status"] == "succeeded"
        assert original.response["robot_state"]["motion"]["state"] == "idle"
        assert "camera_geometry" not in original.response["robot_state"]
        assert sum(response.id == "call-running" for response in session.tool_responses) == 1
        await asyncio.sleep(0.08)
        assert not any(item.get("text") for item in session.realtime)
        await agent._handle_server_content(
            SimpleNamespace(model_turn=None, turn_complete=True, interrupted=False)
        )
        await wait_until(
            lambda: any("[HEARTBEAT]" in item.get("text", "") for item in session.realtime)
        )
        heartbeat_text = next(
            item["text"] for item in session.realtime if item.get("text")
        )
        assert '"tool":null' in heartbeat_text
        assert any(
            kind == "tool.rejected" and payload.get("conflict") is True
            for _, kind, payload in events
        )
        assert any(kind == "tool.response.sent" for _, kind, _ in events)

        agent._finish_active_mission()
        writer.cancel()
        heartbeat.cancel()
        await asyncio.gather(writer, heartbeat, return_exceptions=True)

    asyncio.run(scenario())


def test_active_tool_cancellation_stops_and_fails_without_retry() -> None:
    async def scenario() -> None:
        robot = BlockingRobot()
        events: list[tuple[str, str, dict]] = []
        agent = PersistentGeminiSession(
            "fake-key",
            MissionGuard(robot),
            lambda mission_id, kind, payload: events.append(
                (mission_id, kind, payload)
            ),
            client=SimpleNamespace(),
            camera_interval_s=0,
            heartbeat_idle_s=0,
        )
        agent._active_mission_id = "cancelled-mission"
        agent._connection_state = "ready"
        call = SimpleNamespace(
            name="look_around", args={"quarter_turns": 1}, id="call-cancelled"
        )
        await agent._handle_tool_calls(None, [call])
        await asyncio.to_thread(robot.action_started.wait, 1.0)
        cancellation = SimpleNamespace(
            go_away=None,
            server_content=None,
            tool_call=None,
            tool_call_cancellation=SimpleNamespace(ids=["call-cancelled"]),
        )
        session = ReceivingSession([cancellation])

        await agent._receive_one_turn(session)

        assert robot.stop_calls == 1
        assert robot.look_calls == 1
        assert agent._active_mission_id is None
        rejected = next(payload for _, kind, payload in events if kind == "tool.rejected")
        assert rejected["call_id"] == "call-cancelled"
        assert rejected["result"]["status"] == "cancelled"
        failure = next(payload for _, kind, payload in events if kind == "mission.failed")
        assert "cancelled active tool" in failure["reason"]

    asyncio.run(scenario())
