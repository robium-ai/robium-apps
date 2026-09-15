import asyncio
import json
import threading
import time
from http.server import ThreadingHTTPServer
from urllib import request

from silly_turtlebot.fake_robot import FakeRobot
from silly_turtlebot.mission_server import MissionService, make_handler


class ServiceRobot(FakeRobot):
    def __init__(self, *_args, **_kwargs) -> None:
        super().__init__()

    def health(self):
        return {"status": "ok", "is_docked": self.is_docked}

    def capture_camera_frame(self):
        return b"fake-jpeg"


class FakeBackgroundSession:
    def __init__(self, _api_key, _guard, event_callback, **_kwargs) -> None:
        self.event_callback = event_callback

    def health_snapshot(self):
        return {
            "state": "ready",
            "connection_count": 1,
            "last_camera_frame_age_s": 0.1,
            "camera_send_failures": 0,
        }

    async def submit_instruction(self, mission_id, _instruction, *, update=False):
        assert update is False
        self.event_callback(mission_id, "input.sent", {"kind": "operator"})
        await asyncio.sleep(0.05)
        self.event_callback(
            mission_id,
            "model.text.delta",
            {"text": "Looking"},
        )
        self.event_callback(
            mission_id,
            "tool.started",
            {"name": "look_around", "call_id": "call-1"},
        )
        self.event_callback(
            mission_id,
            "tool.finished",
            {
                "name": "look_around",
                "call_id": "call-1",
                "result": {"status": "succeeded"},
            },
        )
        self.event_callback(mission_id, "mission.completed", {})

    async def abort_active(self, _reason):
        return {"status": "succeeded"}

    async def emergency_stop(self, _reason):
        return {"status": "succeeded"}

    async def shutdown(self):
        return None


def parse_sse(body: bytes) -> list[dict]:
    events = []
    for block in body.decode("utf-8").strip().split("\n\n"):
        data = next(
            (
                line.removeprefix("data: ")
                for line in block.splitlines()
                if line.startswith("data: ")
            ),
            None,
        )
        if data is not None:
            events.append(json.loads(data))
    return events


def test_mission_post_acknowledges_immediately_and_sse_replays_from_last_id():
    service = MissionService(
        "fake-key",
        "http://fake-robot:8088",
        session_factory=FakeBackgroundSession,
        robot_factory=ServiceRobot,
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        with request.urlopen(base_url + "/v1/health") as response:
            assert json.load(response)["gemini_session"]["state"] == "ready"
        with request.urlopen(base_url + "/v1/camera") as response:
            assert response.read() == b"fake-jpeg"
        with request.urlopen(base_url + "/v1/camera/stream") as response:
            assert response.headers["Content-Type"].startswith(
                "multipart/x-mixed-replace"
            )
            assert response.readline() == b"--frame\r\n"
            assert response.readline() == b"Content-Type: image/jpeg\r\n"
            assert response.readline() == b"Content-Length: 9\r\n"
            assert response.readline() == b"\r\n"
            assert response.read(9) == b"fake-jpeg"

        started = time.monotonic()
        mission_request = request.Request(
            base_url + "/v1/missions",
            data=json.dumps({"instruction": "look around"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with request.urlopen(mission_request) as response:
            mission = json.load(response)
            assert response.status == 202
        assert time.monotonic() - started < 0.5
        assert mission["status"] == "accepted"

        mission_id = mission["mission_id"]
        with request.urlopen(base_url + f"/v1/events/{mission_id}") as response:
            assert response.headers["Content-Type"] == "text/event-stream"
            events = parse_sse(response.read())

        assert [event["type"] for event in events] == [
            "mission.accepted",
            "input.sent",
            "model.text.delta",
            "tool.started",
            "tool.finished",
            "mission.completed",
        ]
        assert [event["seq"] for event in events] == [1, 2, 3, 4, 5, 6]

        reconnect = request.Request(
            base_url + f"/v1/events/{mission_id}",
            headers={"Last-Event-ID": "4"},
        )
        with request.urlopen(reconnect) as response:
            replayed = parse_sse(response.read())
        assert [event["seq"] for event in replayed] == [5, 6]
        assert all(event["type"] != "tool.started" for event in replayed)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        service.close()
