from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_live_image_uses_immutable_matched_base_and_capability_gateway():
    dockerfile = (ROOT / "containers/live/Dockerfile").read_text()
    entrypoint = (ROOT / "containers/live/entrypoint.sh").read_text()

    assert "nvcr.io/nvidia/isaac-lab:" in dockerfile
    assert "@sha256:" in dockerfile
    assert "GO2_ARCHIVE_SHA256=" in dockerfile
    assert "DEMO_CAPABILITY is required" in entrypoint
    assert "sha256sum" in entrypoint
    assert "live_demo_patch.py" in entrypoint
    assert '"${isaaclab_root}/isaaclab.sh" -p' in entrypoint
    assert "--headless" in entrypoint
    assert "tar --no-same-owner" in entrypoint


def test_live_image_keeps_an_explicit_non_simulating_setup_mode():
    entrypoint = (ROOT / "containers/live/entrypoint.sh").read_text()

    assert 'DEMO_STARTUP_MODE:-live' in entrypoint
    assert '== "idle"' in entrypoint
    assert "exec sleep infinity" in entrypoint
