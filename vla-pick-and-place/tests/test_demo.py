"""Gateway smoke — the ship bar AGENTS.md requires before an app change is done.

Three tests. It boots the real gateway and drives it the way a visitor does,
and it asserts on PIXELS, not status codes: "the endpoint answered 200" was
true of the version of this page whose viewer displayed nothing at all.

Marked slow: boots a subprocess with a real MuJoCo environment and pulls the
pinned dataset. Run via `make demo-smoke`.
"""

import base64
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

import numpy as np
import pytest

pytestmark = pytest.mark.slow

PORT = 8799  # not 8765: must not collide with a dev gateway the user left up
BASE = f"http://127.0.0.1:{PORT}"
BOOT_TIMEOUT_S = 300
CALL_TIMEOUT_S = 300


def _http(method: str, path: str):
    req = urllib.request.Request(f"{BASE}{path}", method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def _call(api_name: str, data: list, until=None):
    """Invoke a Gradio endpoint, returning the last payload it streamed."""
    req = urllib.request.Request(
        f"{BASE}/ui/gradio_api/call/{api_name}",
        method="POST",
        data=json.dumps({"data": data}).encode(),
        headers={"content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        sub = json.loads(r.read())
    last = None
    deadline = time.time() + CALL_TIMEOUT_S
    stream = urllib.request.Request(f"{BASE}/ui/gradio_api/call/{api_name}/{sub['event_id']}")
    with urllib.request.urlopen(stream, timeout=CALL_TIMEOUT_S) as r:
        for raw in r:
            if time.time() > deadline:
                break
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:") or line == "data: null":
                continue
            payload = json.loads(line[len("data:"):])
            if isinstance(payload, list) and payload:
                last = payload
                if until and until(payload):
                    break
    assert last is not None, f"{api_name} streamed no payload"
    return last


def _image(entry) -> np.ndarray:
    from PIL import Image

    url = entry.get("url") or entry.get("path")
    assert url, f"image payload has no url/path: {entry}"
    if url.startswith("data:"):
        data = base64.b64decode(url.split(",", 1)[1])
    else:
        if not url.startswith("http"):
            url = f"{BASE}/ui/gradio_api/file={url}"
        with urllib.request.urlopen(url, timeout=60) as r:
            data = r.read()
    return np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))


def _assert_real_frame(entry, name):
    frame = _image(entry)
    assert frame.shape == (480, 640, 3), f"{name} {frame.shape}"
    assert frame.mean() > 20, f"{name} is nearly black ({frame.mean():.1f})"
    assert frame.std() > 5, f"{name} is a flat fill"


@pytest.fixture(scope="module")
def gateway(tmp_path_factory):
    log_path = tmp_path_factory.mktemp("demo") / "gateway.log"
    env = {**os.environ, "PORT": str(PORT)}
    env.setdefault("MUJOCO_GL", "cgl" if sys.platform == "darwin" else "egl")
    with open(log_path, "w") as log:
        proc = subprocess.Popen(
            [sys.executable, "-m", "vla_pick_and_place.demo.gateway"],
            env=env, stdout=log, stderr=subprocess.STDOUT,
        )
    deadline = time.time() + BOOT_TIMEOUT_S
    while time.time() < deadline:
        text = log_path.read_text()
        if "DEMO READY" in text or "BOOT FAILED" in text or proc.poll() is not None:
            break
        time.sleep(2)
    if "DEMO READY" not in log_path.read_text():
        proc.kill()
        pytest.fail(f"gateway never reached DEMO READY:\n{log_path.read_text()[-3000:]}")
    yield proc
    if proc.poll() is None:
        proc.kill()


def test_gateway_is_ready_and_guards_its_session(gateway):
    code, st = _http("GET", "/status?session=alice")
    assert code == 200 and st["ready"] is True and st["claimed"] is False

    code, body = _http("POST", "/start?session=alice")
    assert code == 200 and body["ok"] is True

    # A foreign session is refused status and refused shutdown.
    assert _http("GET", "/status?session=bob")[0] == 409
    assert _http("POST", "/shutdown?session=bob")[0] == 403


def test_both_sources_return_real_frames_and_say_which_is_which(gateway):
    """The two claims this page makes. Live simulation must produce a
    non-black frame in radians; playback must announce itself as a recording
    in the dataset's units and never as a policy."""
    live = _call("reset_sim", [0])
    _assert_real_frame(live[0], "overhead")
    _assert_real_frame(live[1], "wrist")
    assert "source <b>simulator</b>" in live[2] and "units radians" in live[2]

    driven = _call(
        "drive", [8, 0.0, -1.5, 1.5, 0.4, 0.0, 0.0],
        until=lambda p: isinstance(p[3], str) and "steps" in p[3],
    )
    step = re.search(r"step (\d+)/", driven[2])
    assert step and int(step.group(1)) > 0, driven[2]
    _assert_real_frame(driven[0], "driven overhead")

    played = _call(
        "play_episode", [0],
        until=lambda p: isinstance(p[3], str) and "replayed" in p[3],
    )
    _assert_real_frame(played[0], "playback overhead")
    assert "dataset:johnsutor/MuJoCoPickAndPlace-v1#0" in played[2]
    assert "lerobot rows" in played[2]
    assert "polic" not in played[2].lower()


def test_shutdown_exits_the_process_and_frees_the_port(gateway):
    _http("POST", "/start?session=alice")
    code, body = _http("POST", "/shutdown?session=alice")
    assert code == 200 and body["bye"] is True
    deadline = time.time() + 10
    while time.time() < deadline and gateway.poll() is None:
        time.sleep(0.2)
    assert gateway.poll() is not None, "gateway still alive after /shutdown"
