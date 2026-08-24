import json
from pathlib import Path

import pytest

from vla_pick_and_place.cli import feasibility
from vla_pick_and_place.diagnostics import read_phase, write_failure, write_phase


def test_phase_marker_is_atomic_and_machine_readable(tmp_path: Path) -> None:
    write_phase(tmp_path, "model_loading")

    marker = json.loads((tmp_path / "phase.json").read_text())
    assert marker["schema_version"] == "1.0.0"
    assert marker["stage"] == "model_loading"
    assert marker["status"] == "running"
    assert marker["timestamp"].endswith("Z")
    assert read_phase(tmp_path) == "model_loading"
    assert not (tmp_path / ".phase.json.tmp").exists()


def test_failure_marker_redacts_credentials_and_records_active_phase(
    tmp_path: Path,
) -> None:
    write_phase(tmp_path, "checkpoint_bootstrap")
    secret = "hf_example-secret-value"

    write_failure(
        tmp_path,
        RuntimeError(f"download rejected bearer {secret}"),
        environment={"HF_TOKEN": secret, "KEEP": "public"},
        return_code=17,
    )

    marker = json.loads((tmp_path / "failure.json").read_text())
    assert marker["schema_version"] == "1.0.0"
    assert marker["stage"] == "checkpoint_bootstrap"
    assert marker["exception_type"] == "RuntimeError"
    assert marker["message"] == "download rejected bearer [REDACTED]"
    assert marker["return_code"] == 17
    assert marker["timestamp"].endswith("Z")
    assert secret not in (tmp_path / "failure.json").read_text()
    assert "KEEP" not in marker
    assert not (tmp_path / ".failure.json.tmp").exists()


def test_failure_marker_redacts_unregistered_hugging_face_token(
    tmp_path: Path,
) -> None:
    write_phase(tmp_path, "model_loading")

    write_failure(
        tmp_path,
        RuntimeError("upstream returned token hf_abcdefghijklmnopqrstuvwxyz123456"),
        environment={},
    )

    assert (
        "hf_abcdefghijklmnopqrstuvwxyz123456"
        not in (tmp_path / "failure.json").read_text()
    )


def test_feasibility_records_exact_model_loading_failure(tmp_path: Path) -> None:
    class FakeCuda:
        @staticmethod
        def reset_peak_memory_stats() -> None:
            return None

    class FakeTorch:
        cuda = FakeCuda()

    def fail_model_load():
        raise ValueError("processor configuration is incompatible")

    with pytest.raises(ValueError, match="processor configuration"):
        feasibility(
            tmp_path,
            torch_module=FakeTorch(),
            runner_factory=fail_model_load,
        )

    marker = json.loads((tmp_path / "failure.json").read_text())
    assert marker["stage"] == "model_loading"
    assert marker["exception_type"] == "ValueError"
