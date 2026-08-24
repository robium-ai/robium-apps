import json
from pathlib import Path

APP_ROOT = Path(__file__).parents[1]


def test_gpu_image_bakes_noninteractive_libero_config() -> None:
    dockerfile = (APP_ROOT / "docker" / "Dockerfile").read_text()
    config_path = APP_ROOT / "docker" / "libero-config.yaml"

    assert (
        "COPY docker/libero-config.yaml /app/libero-config/config.yaml" in dockerfile
    )
    assert "LIBERO_CONFIG_PATH=/app/libero-config" in dockerfile

    config = json.loads(config_path.read_text())
    assert config == {
        "assets": "/opt/libero/libero/libero/assets",
        "bddl_files": "/opt/libero/libero/libero/bddl_files",
        "benchmark_root": "/opt/libero/libero/libero",
        "datasets": "/opt/libero/libero/datasets",
        "init_states": "/opt/libero/libero/libero/init_files",
    }
