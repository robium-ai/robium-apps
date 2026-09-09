import io
import json

from silly_turtlebot.rest_robot import RestRobot


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def test_ros_adapter_posts_semantic_action_and_queues_camera(monkeypatch) -> None:
    requests = []

    def open_request(req, timeout):
        requests.append((req.full_url, req.data, timeout))
        if req.full_url.endswith(
            ("/v1/look-around", "/v1/move-forward", "/v1/dock", "/v1/undock")
        ):
            return Response(json.dumps({"status": "succeeded"}).encode())
        if req.full_url.endswith("/v1/camera/primary"):
            return Response(b"jpeg-from-oakd")
        raise AssertionError(req.full_url)

    monkeypatch.setattr("silly_turtlebot.rest_robot.request.urlopen", open_request)
    robot = RestRobot("http://127.0.0.1:8088")

    forward = robot.move_forward(0.25)
    result = robot.look_around(2)
    assert robot.undock()["status"] == "succeeded"
    assert robot.dock()["status"] == "succeeded"

    assert json.loads(requests[0][1]) == {"distance_m": 0.25}
    assert json.loads(requests[2][1]) == {"quarter_turns": 2}
    assert requests[4][0].endswith("/v1/undock")
    assert requests[5][0].endswith("/v1/dock")
    assert forward["camera_frame"] == "sent_to_model"
    assert result["camera_frame"] == "sent_to_model"
    assert robot.consume_camera_frames() == [b"jpeg-from-oakd", b"jpeg-from-oakd"]
    assert robot.consume_camera_frames() == []

    requests.clear()
    external = RestRobot(
        "http://127.0.0.1:8088", camera_url="http://orin:8081"
    )
    monkeypatch.setattr(
        "silly_turtlebot.rest_robot.request.urlopen",
        lambda req, timeout: Response(b"jpeg-from-orin")
        if req.full_url.endswith("/frame.jpg")
        else Response(
            json.dumps({"status": "ok", "cameras": {}}).encode()
            if req.full_url.endswith("/v1/health")
            else json.dumps({"status": "ok", "fresh": True, "age_s": 0.1}).encode()
        ),
    )
    assert external.capture_camera_frame() == b"jpeg-from-orin"
    assert external.health()["cameras"]["primary"]["fresh"] is True
