import json
from pathlib import Path

APP_ROOT = Path(__file__).parents[1]


def test_gpu_image_bakes_noninteractive_libero_config() -> None:
    dockerfile = (APP_ROOT / "docker" / "Dockerfile").read_text()
    config_path = APP_ROOT / "docker" / "libero-config.yaml"

    assert "COPY docker/libero-config.yaml /app/libero-config/config.yaml" in dockerfile
    assert "LIBERO_CONFIG_PATH=/app/libero-config" in dockerfile
    assert "cp -a /opt/libero/libero/libero/assets/." in dockerfile
    assert "/app/.venv/lib/python3.10/site-packages/libero/libero/assets/" in dockerfile
    assert "PYTHONPATH=/opt/libero" not in dockerfile
    assert "VLA_STAGED_CHECKPOINT_PATH=/tmp/pi05-libero-v044" in dockerfile
    assert "VLA_POLICY_EXECUTION=eager" in dockerfile
    assert "VLA_EVALUATION_OUTPUT=/models/issue-69-evaluation" in dockerfile
    assert "gcc libegl1" in dockerfile
    assert "libosmesa6 python3.10 python3.10-dev python3.10-venv" in dockerfile
    assert dockerfile.count("--mount=type=cache,target=/root/.cache/uv") == 4
    assert dockerfile.count("COPY pyproject.toml uv.lock ./") == 2
    assert dockerfile.count("COPY README.md ./") == 2
    assert "COPY pyproject.toml uv.lock README.md ./" not in dockerfile

    config = json.loads(config_path.read_text())
    assert config == {
        "assets": "/opt/libero/libero/libero/assets",
        "bddl_files": "/opt/libero/libero/libero/bddl_files",
        "benchmark_root": "/opt/libero/libero/libero",
        "datasets": "/opt/libero/libero/datasets",
        "init_states": "/opt/libero/libero/libero/init_files",
    }
