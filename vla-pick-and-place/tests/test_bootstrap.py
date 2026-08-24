from pathlib import Path

import pytest

from vla_pick_and_place.bootstrap import bootstrap_checkpoint, offline_environment
from vla_pick_and_place.config import (
    CHECKPOINT_ID,
    CHECKPOINT_MODEL_BYTES,
    CHECKPOINT_MODEL_SHA256,
    CHECKPOINT_REVISION,
)
from vla_pick_and_place.real import REQUIRED_CHECKPOINT_FILES
from vla_pick_and_place.startup import launch_feasibility, launch_gateway


def _snapshot(path: Path, *, model: bytes) -> None:
    for name in REQUIRED_CHECKPOINT_FILES:
        (path / name).write_bytes(model if name == "model.safetensors" else b"x")


def test_bootstrap_downloads_exact_snapshot_and_writes_revision_last(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []
    model = b"verified-model"
    monkeypatch.setattr(
        "vla_pick_and_place.bootstrap.CHECKPOINT_MODEL_BYTES", len(model)
    )
    monkeypatch.setattr(
        "vla_pick_and_place.bootstrap.CHECKPOINT_MODEL_SHA256",
        "3326723577b96bc7d05ecdb8a32ac917ce7eb053152f145b609635ebdbaf8d46",
    )
    (tmp_path / "REVISION").write_text("stale\n")

    def download(**kwargs):
        calls.append(kwargs)
        assert not (tmp_path / "REVISION").exists()
        _snapshot(tmp_path, model=model)

    bootstrap_checkpoint(tmp_path, token="secret-token", download=download)

    assert calls == [
        {
            "repo_id": CHECKPOINT_ID,
            "revision": CHECKPOINT_REVISION,
            "local_dir": tmp_path,
            "allow_patterns": list(REQUIRED_CHECKPOINT_FILES),
            "token": "secret-token",
        }
    ]
    assert (tmp_path / "REVISION").read_text() == f"{CHECKPOINT_REVISION}\n"


def test_bootstrap_hash_failure_leaves_snapshot_unmarked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = b"wrong"
    monkeypatch.setattr(
        "vla_pick_and_place.bootstrap.CHECKPOINT_MODEL_BYTES", len(model)
    )

    def download(**_kwargs):
        _snapshot(tmp_path, model=model)

    with pytest.raises(RuntimeError, match="model SHA-256 mismatch"):
        bootstrap_checkpoint(tmp_path, token="secret-token", download=download)

    assert not (tmp_path / "REVISION").exists()


def test_offline_environment_removes_hub_token() -> None:
    result = offline_environment(
        {"HF_TOKEN": "secret", "KEEP": "value", "HF_HUB_OFFLINE": "0"}
    )

    assert "HF_TOKEN" not in result
    assert result["KEEP"] == "value"
    assert result["HF_HUB_OFFLINE"] == "1"
    assert result["TRANSFORMERS_OFFLINE"] == "1"
    assert CHECKPOINT_MODEL_BYTES == 7_473_096_344
    assert CHECKPOINT_MODEL_SHA256 == (
        "877b3ec1130548b69af7f8aeef3ec9d3fc7738040f0b9beb490857ec970997ae"
    )


def test_startup_uses_complete_checkpoint_without_hub_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []
    monkeypatch.setattr(
        "vla_pick_and_place.startup.validate_checkpoint_snapshot", lambda _path: None
    )
    monkeypatch.setattr(
        "vla_pick_and_place.startup.cuda_preflight", lambda _output: calls.append("cuda")
    )
    monkeypatch.setattr(
        "vla_pick_and_place.startup.bootstrap_checkpoint",
        lambda *_args, **_kwargs: pytest.fail("complete checkpoint was downloaded"),
    )

    launch_gateway(
        checkpoint_path=tmp_path,
        environment={"HF_TOKEN": "secret", "KEEP": "value"},
        execute=lambda executable, command, environment: calls.append(
            (executable, command, environment)
        ),
    )

    assert calls[0] == "cuda"
    assert len(calls) == 2
    executable, command, environment = calls[1]
    assert executable == command[0]
    assert command[-2:] == ["-m", "vla_pick_and_place.gateway"]
    assert "HF_TOKEN" not in environment
    assert environment["KEEP"] == "value"
    assert environment["HF_HUB_OFFLINE"] == "1"


def test_startup_bootstraps_incomplete_checkpoint_before_offline_gateway(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []

    def incomplete(_path: Path) -> None:
        raise RuntimeError("checkpoint incomplete")

    monkeypatch.setattr(
        "vla_pick_and_place.startup.validate_checkpoint_snapshot", incomplete
    )
    monkeypatch.setattr(
        "vla_pick_and_place.startup.cuda_preflight", lambda _output: calls.append("cuda")
    )
    monkeypatch.setattr(
        "vla_pick_and_place.startup.bootstrap_checkpoint",
        lambda path, *, token: calls.append(("bootstrap", path, token)),
    )

    launch_gateway(
        checkpoint_path=tmp_path,
        environment={"HF_TOKEN": "secret"},
        execute=lambda executable, command, environment: calls.append(
            ("execute", executable, command, environment)
        ),
    )

    assert calls[0] == "cuda"
    assert calls[1] == ("bootstrap", tmp_path, "secret")
    assert calls[2][0] == "execute"
    assert "HF_TOKEN" not in calls[2][3]
    assert calls[2][3]["TRANSFORMERS_OFFLINE"] == "1"


def test_feasibility_startup_preflights_then_runs_once_and_holds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkpoint = tmp_path / "checkpoint"
    output = tmp_path / "evidence"
    calls = []
    monkeypatch.setattr(
        "vla_pick_and_place.startup.cuda_preflight",
        lambda target: calls.append(("cuda", target)),
    )
    monkeypatch.setattr(
        "vla_pick_and_place.startup.validate_checkpoint_snapshot",
        lambda _path: None,
    )

    launch_feasibility(
        checkpoint_path=checkpoint,
        output=output,
        environment={"HF_TOKEN": "secret", "KEEP": "value"},
        run=lambda command, **kwargs: calls.append(("run", command, kwargs)),
        hold=lambda: calls.append(("hold",)),
    )

    assert calls[0] == ("cuda", output / "cuda-preflight.json")
    assert calls[1][0] == "run"
    assert calls[1][1][-3:] == ["feasibility", "--output", str(output)]
    assert calls[1][2]["check"] is True
    assert "HF_TOKEN" not in calls[1][2]["env"]
    assert calls[1][2]["env"]["KEEP"] == "value"
    assert calls[2] == ("hold",)
