from fastapi.testclient import TestClient

from vla_pick_and_place.gateway import create_gateway
from vla_pick_and_place.rollout import (
    DeterministicFakePolicy,
    FixtureEnvironment,
    RolloutRunner,
)

CAPABILITY = "cap_0123456789abcdefghijklmnopqrstuvwxyzABCDEFG"


def test_gateway_hides_root_missing_and_foreign_capabilities(tmp_path):
    runner = RolloutRunner(FixtureEnvironment(tmp_path), DeterministicFakePolicy())
    app = create_gateway(capability=CAPABILITY, runner=runner, terminate=lambda: None)
    client = TestClient(app)

    assert client.get("/").status_code == 404
    assert client.get("/status").status_code == 404
    assert client.get("/c/foreign/status").status_code == 404
    assert client.get(f"/c/{CAPABILITY}/status").status_code == 200
    assert client.get(f"/c/{CAPABILITY}/ui/").status_code == 200


def test_claim_is_idempotent_and_shutdown_terminates_after_response(tmp_path):
    terminated = []
    runner = RolloutRunner(FixtureEnvironment(tmp_path), DeterministicFakePolicy())
    client = TestClient(
        create_gateway(
            capability=CAPABILITY,
            runner=runner,
            terminate=lambda: terminated.append(True),
        )
    )

    path = f"/c/{CAPABILITY}"
    assert client.post(f"{path}/claim").json()["claimed"] is True
    assert client.post(f"{path}/claim").json()["claimed"] is True
    response = client.post(f"{path}/shutdown")
    assert response.status_code == 200
    assert response.json() == {"deleting": True}
    assert terminated == [True]


def test_streamed_fake_rollout_returns_frames_and_simulator_outcome(tmp_path):
    runner = RolloutRunner(
        FixtureEnvironment(tmp_path, success=True), DeterministicFakePolicy()
    )
    client = TestClient(
        create_gateway(capability=CAPABILITY, runner=runner, terminate=lambda: None)
    )

    response = client.post(
        f"/c/{CAPABILITY}/rollout",
        json={"state_id": 0, "prompt": "put the bowl on the plate"},
    )
    body = response.json()
    assert response.status_code == 200
    assert body["success"] is True
    assert body["frame_count"] > 0
    assert body["prompt_class"] == "benchmark-supported"


def test_ready_window_reports_remaining_time_and_refuses_expired_rollouts(tmp_path):
    now = [100.0]
    runner = RolloutRunner(
        FixtureEnvironment(tmp_path, success=True), DeterministicFakePolicy()
    )
    client = TestClient(
        create_gateway(
            capability=CAPABILITY,
            runner=runner,
            terminate=lambda: None,
            ready_seconds=10,
            clock=lambda: now[0],
        )
    )
    path = f"/c/{CAPABILITY}"
    assert client.get(f"{path}/status").json()["remaining_s"] == 10
    now[0] = 110.0
    assert client.get(f"{path}/status").json()["phase"] == "expired"
    response = client.post(
        f"{path}/rollout",
        json={"state_id": 0, "prompt": "put the bowl on the plate"},
    )
    assert response.status_code == 410
    assert response.json() == {"detail": "session expired"}
