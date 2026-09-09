import json
import threading
from urllib import request

from silly_turtlebot.mission_server import make_handler
from http.server import ThreadingHTTPServer


class FakeMissionService:
    def health(self):
        return {"status": "ok", "robot": {"status": "ok"}}

    def run(self, instruction, camera_source="primary"):
        return {
            "status": "succeeded",
            "response": f"accepted: {instruction}",
            "tool_calls": [{"name": "look_around", "result": {"status": "succeeded"}}],
        }

    def stop(self):
        return {"status": "succeeded"}

    def camera(self):
        return b"fake-jpeg"


def test_mission_console_http_contract():
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(FakeMissionService()))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        health = json.load(request.urlopen(base_url + "/v1/health"))
        assert health["status"] == "ok"

        with request.urlopen(base_url + "/v1/camera") as response:
            assert response.headers["Content-Type"] == "image/jpeg"
            assert response.read() == b"fake-jpeg"

        mission_request = request.Request(
            base_url + "/v1/missions",
            data=json.dumps({"instruction": "look around"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        mission = json.load(request.urlopen(mission_request))
        assert mission["response"] == "accepted: look around"
        assert mission["tool_calls"][0]["name"] == "look_around"

        stop_request = request.Request(base_url + "/v1/stop", data=b"{}")
        assert json.load(request.urlopen(stop_request))["status"] == "succeeded"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
