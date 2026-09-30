import http.client
import json
import struct
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from lego_stackchan_drive import faces
from lego_stackchan_drive.faces import (
    BMP_SIZE,
    EMOTIONS,
    MAX_PCM_BYTES,
    FaceClient,
    make_panel,
    validate_action,
    validate_pcm,
)


@pytest.fixture(autouse=True)
def voice_inventory(monkeypatch):
    # Panel tests must also run on a fresh checkout without neural model caches.
    monkeypatch.setattr(faces, "english_voices", lambda: ("am_puck", "bf_emma"))
    monkeypatch.setattr(faces, "available_voices", lambda: (("Samantha", "en_US", "Hello"),))


@pytest.fixture
def serve():
    servers = []

    def start(handler):
        server = HTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append((server, thread))
        return server.server_port

    yield start
    for server, thread in servers:
        server.shutdown()
        server.server_close()
        thread.join(2)


class FakeFace:
    def __init__(self):
        self.actions = []
        self.offline = False

    def state(self):
        if self.offline:
            raise TimeoutError("private endpoint details")
        return {"emotion": "neutral", "visible_emotion": "neutral", "renderer_ready": True}

    def send(self, **action):
        self.actions.append(action)
        return self.state()


def request(port, path, action=None, origin=True):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    headers = {"Content-Type": "application/json"}
    if origin:
        headers["Origin"] = f"http://127.0.0.1:{port}"
    connection.request("POST" if action is not None else "GET", path,
                       None if action is None else json.dumps(action), headers)
    response = connection.getresponse()
    result = response.status, response.read()
    connection.close()
    return result


def test_panel_only_valid_same_origin_actions_reach_device(serve):
    device = FakeFace()
    port = serve(make_panel(device, "private-token"))
    for path, action, origin, expected in [
        ("/action", {"emotion": "happy"}, True, 404),
        ("/private-token/action", {"emotion": "happy"}, False, 403),
        ("/private-token/action", {"emotion": "happy", "talking": 1}, True, 400),
        ("/private-token/action", {"emotion": "happy"}, True, 200),
    ]:
        status, _ = request(port, path, action, origin)
        assert status == expected
    assert device.actions == [{"emotion": "happy"}]


def test_panel_recovers_when_camera_returns_without_robot(serve):
    device = FakeFace()
    port = serve(make_panel(device, "private-token"))
    device.offline = True
    status, data = request(port, "/private-token/state")
    assert status == 503 and b"private endpoint" not in data
    device.offline = False
    assert request(port, "/private-token/state")[0] == 200


@pytest.mark.parametrize("action", [
    {}, [], {"emotion": "unknown"}, {"emotion": None}, {"talking": "true"},
    {"talking": 1}, {"motor": 75}, {"auto_cycle": None},
])
def test_bad_actions_rejected(action):
    with pytest.raises(ValueError):
        validate_action(action)


def test_face_client_authenticates_and_checks_snapshot_contract(serve):
    calls = []
    bitmap = bytearray(BMP_SIZE)
    bitmap[:2] = b"BM"
    struct.pack_into("<I", bitmap, 10, 54)
    struct.pack_into("<IiiHH", bitmap, 14, 40, 320, -240, 1, 24)

    class Device(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            calls.append((self.path, self.headers.get("X-Stream-Key")))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(bitmap if self.path == "/face.bmp" else json.dumps({
                "emotion": "happy", "visible_emotion": "happy", "renderer_ready": True,
            }).encode())

        def do_POST(self):
            calls.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.do_GET()

    client = FaceClient("http://127.0.0.1/stream", "private-key", port=serve(Device))
    for emotion in EMOTIONS:
        assert client.send(emotion=emotion)["renderer_ready"]
    assert client.snapshot() == bitmap
    assert all(call[1] == "private-key" for call in calls if isinstance(call, tuple))
    assert [call["emotion"] for call in calls if isinstance(call, dict)] == list(EMOTIONS)
    bitmap[0] = 0
    with pytest.raises(RuntimeError, match="snapshot"):
        client.snapshot()


@pytest.mark.parametrize("pcm", [b"", b"x", b"x" * (MAX_PCM_BYTES + 2), "audio"])
def test_bad_speech_payload_rejected_before_upload(pcm):
    with pytest.raises(ValueError):
        validate_pcm(pcm)


def test_speech_uses_same_authenticated_pcm_and_refuses_queue(serve):
    captured = []

    class Device(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            captured.append((self.path, self.headers.get("X-Stream-Key"),
                             self.headers.get("Content-Type"),
                             self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(202 if len(captured) == 1 else 409)
            self.end_headers()
            self.wfile.write(b'{"clip_id":1,"phase":"preparing"}')

    client = FaceClient("http://127.0.0.1/stream", "private-key", port=serve(Device))
    pcm = b"\x00\x00\xff\x7f" * 100
    assert client.speak_pcm(pcm)["clip_id"] == 1
    assert captured == [("/speech", "private-key", "application/octet-stream", pcm)]
    with pytest.raises(RuntimeError, match="already speaking"):
        client.speak_pcm(pcm)


def test_panel_uses_neural_default_and_rejects_busy_or_unknown_voice(serve, monkeypatch):
    synthesized = []
    uploaded = []
    waits = []
    monkeypatch.setattr(faces.time, "sleep", lambda seconds: waits.append(seconds))
    device = FakeFace()
    device.busy = False
    device.speech_state = lambda: {"busy": device.busy}
    device.speak_pcm = lambda pcm: uploaded.append(pcm) or {"phase": "preparing"}

    def synthesize(text, voice):
        synthesized.append((text, voice))
        return b"\x00\x00"

    monkeypatch.setattr(faces, "synthesize_speech", synthesize)
    port = serve(make_panel(device, "token"))
    assert request(port, "/token/speak", {"text": "Hello"})[0] == 202
    assert synthesized == [("Hello", "kokoro:am_puck")]
    assert len(waits) == 1 and 4.5 < waits[0] <= 5
    device.busy = True
    assert request(port, "/token/speak", {"text": "Another"})[0] == 409
    device.busy = False
    assert request(port, "/token/speak", {"text": "Hello", "voice": "kokoro:unknown"})[0] == 400
    assert len(synthesized) == len(uploaded) == 1


def test_panel_head_controls_only_allow_explicit_same_origin_modes(serve):
    device = FakeFace()
    commands = []
    device.head_state = lambda: {"manual_posing": True, "release_applied": True}
    device.set_head = lambda mode: commands.append(mode) or device.head_state()
    port = serve(make_panel(device, "token"))
    assert request(port, "/token/head")[0] == 200
    assert request(port, "/token/head", {"mode": "resume"}, origin=False)[0] == 403
    assert request(port, "/token/head", {"mode": "absolute"})[0] == 400
    assert request(port, "/token/head", {"mode": "release", "pan": 1})[0] == 400
    for mode in ("release", "resume"):
        assert request(port, "/token/head", {"mode": mode})[0] == 200
    assert commands == ["release", "resume"]


def test_mac_speech_waits_five_seconds_and_refuses_duplicate_takes(monkeypatch):
    import time
    import wave
    from pathlib import Path

    played = []
    monkeypatch.setattr(faces, "synthesize_speech", lambda text, voice: b"\x00\x00" * 240)

    def playback(args, **kwargs):
        with wave.open(args[1], "rb") as audio:
            assert audio.getframerate() == 24000 and audio.getnchannels() == 1
        played.append((time.monotonic(), args[1]))

    monkeypatch.setattr(faces.subprocess, "run", playback)
    mac = faces.MacSpeech()
    started = time.monotonic()
    assert mac.start("Hello", "kokoro:am_puck")
    assert not mac.start("Duplicate", "kokoro:am_puck")
    deadline = started + 7
    while mac.state()["busy"] and time.monotonic() < deadline:
        time.sleep(.02)
    assert mac.state()["phase"] == "complete"
    assert len(played) == 1 and played[0][0] - started >= 5
    assert not Path(played[0][1]).exists()


def test_mac_speech_panel_independent_of_offline_robot_and_checks_origin(serve):
    class Mac:
        def __init__(self):
            self.calls = []

        def state(self):
            return {"busy": bool(self.calls), "phase": "preparing"}

        def start(self, text, voice):
            if self.calls:
                return False
            self.calls.append((text, voice))
            return True

    device = FakeFace()
    device.offline = True
    mac = Mac()
    port = serve(make_panel(device, "token", mac))
    line = {"text": "Hello", "voice": "kokoro:am_puck"}
    assert request(port, "/token/mac-speech")[0] == 200
    assert request(port, "/token/mac-speak", line, origin=False)[0] == 403
    assert request(port, "/token/mac-speak", {"text": ""})[0] == 400
    assert request(port, "/token/mac-speak", line)[0] == 202
    assert request(port, "/token/mac-speak", line)[0] == 409
    assert mac.calls == [("Hello", "kokoro:am_puck")]


def test_drive_panel_retains_faces_and_blocks_head_changes_while_driving(serve):
    class Drive:
        active = False

        def state(self):
            return {"active": self.active, "phase": "running" if self.active else "idle"}

        def start(self):
            if self.active:
                return False
            self.active = True
            return True

        def stop(self):
            self.active = False
            return self.state()

    drive = Drive()
    face = FakeFace()
    port = serve(make_panel(face, "token", drive_mode=drive))
    assert request(port, '/token/drive', {'action': 'start'}, origin=False)[0] == 403
    assert request(port, '/token/drive', {'action': 'shell'})[0] == 400
    assert request(port, '/token/drive', {'action': 'start'})[0] == 202
    assert request(port, '/token/drive', {'action': 'start'})[0] == 409
    assert request(port, '/token/head', {'mode': 'release'})[0] == 409
    assert request(port, '/token/action', {'emotion': 'happy'})[0] == 200
    assert request(port, '/token/drive', {'action': 'stop'})[0] == 202
    assert not drive.active
