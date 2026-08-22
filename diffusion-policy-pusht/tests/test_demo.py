"""Real-checkpoint hosted-demo smoke; run with ``make demo-smoke``.

The ship bar boots the session gateway, verifies claim isolation, streams
direct RGB frames through the mounted Gradio API, and completes benchmark and
out-of-distribution layouts. Policy success is enforced by the benchmark
manifest, not by picking a convenient browser seed.
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
from PIL import Image

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
def gateway(tmp_path_factory):
    log_path = tmp_path_factory.mktemp("demo") / "app.log"
    env = {**os.environ, "PORT": str(PORT)}
    with open(log_path, "w") as log:
        proc = subprocess.Popen(
            [sys.executable, "-m", "diffusion_policy_pusht.demo.gateway"],
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
        pytest.fail(f"gateway never reached DEMO READY in {BOOT_TIMEOUT_S}s:\n{log_path.read_text()[-3000:]}")
    yield proc
    if proc.poll() is None:
        proc.kill()


def _run_episode_via_api(payload: list) -> tuple[str, str]:
    code, sub = _http("POST", "/ui/gradio_api/call/run_episode", {"data": payload})
    assert code == 200 and "event_id" in sub, sub

    req = urllib.request.Request(f"{BASE}/ui/gradio_api/call/run_episode/{sub['event_id']}")
    final_status = None
    final_result = None
    frame_html = None
    deadline = time.time() + EPISODE_TIMEOUT_S
    with urllib.request.urlopen(req, timeout=EPISODE_TIMEOUT_S) as r:
        for raw in r:
            if time.time() > deadline:
                break
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:") or line == "data: null":
                continue
            payload_ = json.loads(line[len("data:"):])
            if isinstance(payload_, list) and len(payload_) == 4:
                if isinstance(payload_[0], str) and "data:image/png;base64," in payload_[0]:
                    frame_html = payload_[0]
                final_status = payload_[1]
                final_result = payload_[3]
                if any(state in final_status for state in ("solved", "partial progress", "stopped")):
                    break
    assert final_status is not None, "no status updates arrived on the SSE stream"
    assert any(state in final_status for state in ("solved", "partial progress")), (
        f"episode never finished: {final_status!r}"
    )
    assert isinstance(final_result, str), "no verdict HTML arrived"
    assert frame_html, "no inline RGB frame arrived"
    match = re.search(r'src="data:image/png;base64,([^"]+)"', frame_html)
    assert match, "inline frame has no PNG data URL"
    image = np.asarray(Image.open(io.BytesIO(base64.b64decode(match.group(1)))))
    assert image.shape[:2] == (96, 96)
    assert float(image.std()) > 1.0, "direct frame is black or flat"
    return final_status, final_result


def test_gateway_contract_and_trained_shape_episode_completes(gateway):
    from diffusion_policy_pusht import config

    code, status_body = _http("GET", "/status?session=alice")
    assert code == 200 and status_body["ready"] is True
    assert status_body["claimed"] is False
    assert status_body["fleet"]["budget"] == config.DEMO_FLEET_BUDGET
    code, body = _http("POST", "/start?session=alice")
    assert code == 200 and body["ok"] is True
    code, status_body = _http("GET", "/status?session=alice")
    assert code == 200 and status_body["claimed"] is True
    assert _http("GET", "/status?session=bob")[0] == 409
    assert _http("POST", "/shutdown?session=bob")[0] == 403

    manifest = json.loads(config.DEMO_LADDER_MANIFEST.read_text())
    status, result = _run_episode_via_api(
        [manifest["selected_model"], "fast", "T", manifest["live_seed"]]
    )
    assert "raw coverage" in status or "solved" in status
    assert "seed " in result


def test_out_of_distribution_shape_episode_completes(gateway):
    from diffusion_policy_pusht import config

    manifest = json.loads(config.DEMO_LADDER_MANIFEST.read_text())
    _, result = _run_episode_via_api(
        [manifest["selected_model"], "fast", "L", manifest["live_seed"] + 1]
    )
    assert "out-of-distribution" in result, f"OOD run not labeled as such: {result!r}"


def test_episode_runner_shape_roundtrip():
    from diffusion_policy_pusht import config
    from diffusion_policy_pusht.demo.episode_runner import EpisodeRunner
    from diffusion_policy_pusht.demo.ui import CSS

    assert ".dp-stream-surface" in CSS
    assert 'input[type="radio"]:checked' in CSS
    assert "box-shadow:inset 0 0 0 4px" in CSS
    assert "transition:none" not in CSS
    assert "opacity:1 !important" not in CSS

    manifest = json.loads(config.DEMO_LADDER_MANIFEST.read_text())
    assert {model["name"] for model in manifest["models"]}
    assert manifest["selected_model"] == "official-175k"
    assert manifest["official_eval_seed_range"] == [1000, 1499]
    published = next(model for model in manifest["models"] if model["name"] == "official-175k")
    assert "avg_max_normalized_reward" in published["evidence"]["metrics"]
    assert "avg_max_raw_coverage" not in published["evidence"]["metrics"]
    seed = manifest["live_seed"] + 2
    frame = EpisodeRunner.preview("Z", seed)
    assert frame.shape == (96, 96, 3)
    assert np.array_equal(frame, EpisodeRunner.preview("Z", seed)), "same seed changed the layout"

    with pytest.raises(ValueError, match="unknown shape"):
        EpisodeRunner.preview("X", 0)

    runner = EpisodeRunner(device=config.demo_device())
    episode = runner.run(
        runner.default_model,
        inference_mode="fast",
        shape="T",
        seed=seed,
    )
    first = next(episode)
    assert first.frame.shape == (96, 96, 3)
    runner.cancel()
    remaining = list(episode)
    assert remaining[-1].done and remaining[-1].aborted
    assert not runner.busy, "cancellation leaked the rollout lock"
