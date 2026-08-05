"""Demo tests, all marked slow (real checkpoint loads); run via
`make demo-smoke`, not the default suite.

The ship bar for the session-blind app: it boots to DEMO READY, one episode
completes on the training-distribution shape (T) through the Gradio API,
and one completes on an out-of-distribution shape (L). Completion is the
assertion — success at this training scale would be theater.
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest
import rerun as rr

pytestmark = pytest.mark.slow

PORT = 8798  # NOT 8765 (a dev demo may be up) and NOT 8799 (vla's test port)
BASE = f"http://127.0.0.1:{PORT}"
BOOT_TIMEOUT_S = 180
EPISODE_TIMEOUT_S = 300


def _http(method: str, path: str, body: dict | None = None):
    req = urllib.request.Request(
        f"{BASE}{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"content-type": "application/json"} if body is not None else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    log_path = tmp_path_factory.mktemp("demo") / "app.log"
    env = {**os.environ, "PORT": str(PORT)}
    with open(log_path, "w") as log:
        proc = subprocess.Popen(
            [sys.executable, "-m", "imitation_manipulation.demo.app"],
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    deadline = time.time() + BOOT_TIMEOUT_S
    while time.time() < deadline:
        text = log_path.read_text()
        if "DEMO READY" in text or proc.poll() is not None:
            break
        time.sleep(2)
    if "DEMO READY" not in log_path.read_text():
        proc.kill()
        pytest.fail(f"app never reached DEMO READY in {BOOT_TIMEOUT_S}s:\n{log_path.read_text()[-3000:]}")
    yield proc
    if proc.poll() is None:
        proc.kill()


def _run_episode_via_api(payload: list) -> str:
    code, sub = _http("POST", "/gradio_api/call/run_episode", {"data": payload})
    assert code == 200 and "event_id" in sub, sub

    req = urllib.request.Request(f"{BASE}/gradio_api/call/run_episode/{sub['event_id']}")
    final_status = None
    deadline = time.time() + EPISODE_TIMEOUT_S
    with urllib.request.urlopen(req, timeout=EPISODE_TIMEOUT_S) as r:
        for raw in r:
            if time.time() > deadline:
                break
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:") or line == "data: null":
                continue
            payload_ = json.loads(line[len("data:"):])
            if isinstance(payload_, list) and payload_ and isinstance(payload_[-1], str):
                final_status = payload_[-1]
                if "finished at step" in final_status:
                    break
    assert final_status is not None, "no status updates arrived on the SSE stream"
    assert "finished at step" in final_status, f"episode never finished: {final_status!r}"
    return final_status


def test_trained_shape_episode_completes(app):
    # "1k" — the weakest rung: honest flailing, but completion is the bar.
    status = _run_episode_via_api(["1k", "T"])
    assert "reward" in status, f"verdict lacks the honest metric: {status!r}"


def test_out_of_distribution_shape_episode_completes(app):
    status = _run_episode_via_api(["5k", "L"])
    assert "out-of-distribution" in status, f"OOD run not labeled as such: {status!r}"


def test_episode_runner_shape_roundtrip():
    from imitation_manipulation.demo.episode_runner import EpisodeRunner

    runner = EpisodeRunner()
    assert set(runner.rungs) == {"1k", "3k", "5k", "10k"}

    rec = rr.RecordingStream(application_id="imitation_manipulation_test", recording_id="t0")
    events = list(runner.run("1k", rec, shape="Z"))
    assert events, "no StepEvents yielded"
    last = events[-1]
    assert last.done is True
    assert 0.0 <= last.max_reward <= 1.0
    assert last.step <= last.total <= 300
    assert not runner.busy

    with pytest.raises(ValueError, match="unknown shape"):
        list(runner.run("1k", rec, shape="X"))
