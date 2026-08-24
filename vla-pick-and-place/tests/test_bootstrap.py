from pathlib import Path

import pytest

from vla_pick_and_place.bootstrap import bootstrap_checkpoint, offline_environment
from vla_pick_and_place.config import (
    CHECKPOINT_ID,
    CHECKPOINT_MODEL_BYTES,
    CHECKPOINT_MODEL_SHA256,
    CHECKPOINT_REVISION,
    TOKENIZER_FILES,
    TOKENIZER_ID,
    TOKENIZER_REVISION,
)
from vla_pick_and_place.diagnostics import read_phase
from vla_pick_and_place.real import REQUIRED_CHECKPOINT_FILES
from vla_pick_and_place.startup import (
    launch_feasibility,
    launch_gateway,
    stage_checkpoint,
)


def _snapshot(path: Path, *, model: bytes) -> None:
    for name in REQUIRED_CHECKPOINT_FILES:
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(model if name == "model.safetensors" else b"x")
    (path / "tokenizer" / "REVISION").write_text(f"{TOKENIZER_REVISION}\n")


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
        if kwargs["repo_id"] == CHECKPOINT_ID:
            for name in REQUIRED_CHECKPOINT_FILES:
                if name.startswith("tokenizer/"):
                    continue
                target = tmp_path / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(model if name == "model.safetensors" else b"x")
        else:
            for name in TOKENIZER_FILES:
                (tmp_path / "tokenizer" / name).parent.mkdir(
                    parents=True, exist_ok=True
                )
                (tmp_path / "tokenizer" / name).write_bytes(b"tokenizer")

    bootstrap_checkpoint(tmp_path, token="secret-token", download=download)

    assert calls == [
        {
            "repo_id": CHECKPOINT_ID,
            "revision": CHECKPOINT_REVISION,
            "local_dir": tmp_path,
            "allow_patterns": [
                name
                for name in REQUIRED_CHECKPOINT_FILES
                if not name.startswith("tokenizer/")
            ],
            "token": "secret-token",
        },
        {
            "repo_id": TOKENIZER_ID,
            "revision": TOKENIZER_REVISION,
            "local_dir": tmp_path / "tokenizer",
            "allow_patterns": list(TOKENIZER_FILES),
            "token": "secret-token",
        },
    ]
    assert (tmp_path / "REVISION").read_text() == f"{CHECKPOINT_REVISION}\n"
    assert (
        tmp_path / "tokenizer" / "REVISION"
    ).read_text() == f"{TOKENIZER_REVISION}\n"


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


def test_bootstrap_tokenizer_access_failure_leaves_snapshot_unmarked(
    tmp_path: Path,
) -> None:
    (tmp_path / "REVISION").write_text("stale\n")
    tokenizer_revision = tmp_path / "tokenizer" / "REVISION"
    tokenizer_revision.parent.mkdir()
    tokenizer_revision.write_text("stale\n")

    def download(**kwargs):
        if kwargs["repo_id"] == TOKENIZER_ID:
            raise PermissionError("gated tokenizer denied")

    with pytest.raises(PermissionError, match="gated tokenizer denied"):
        bootstrap_checkpoint(tmp_path, token="secret-token", download=download)

    assert not (tmp_path / "REVISION").exists()
    assert not tokenizer_revision.exists()


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


def test_stage_checkpoint_replaces_target_then_validates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "persistent"
    target = tmp_path / "staged"
    source.mkdir()
    target.mkdir()
    (source / "model.safetensors").write_bytes(b"new")
    (target / "stale").write_bytes(b"old")
    validated = []
    monkeypatch.setattr(
        "vla_pick_and_place.startup.validate_checkpoint_snapshot",
        lambda path: validated.append(path),
    )

    result = stage_checkpoint(source, target)

    assert result == target
    assert (target / "model.safetensors").read_bytes() == b"new"
    assert not (target / "stale").exists()
    assert validated == [target]


def test_startup_passes_staged_checkpoint_to_offline_gateway(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    persistent = tmp_path / "persistent"
    staged = tmp_path / "staged"
    persistent.mkdir()
    calls = []
    monkeypatch.setattr(
        "vla_pick_and_place.startup.cuda_preflight", lambda _output: None
    )
    monkeypatch.setattr(
        "vla_pick_and_place.startup.validate_checkpoint_snapshot", lambda _path: None
    )
    monkeypatch.setattr(
        "vla_pick_and_place.startup.stage_checkpoint",
        lambda source, target: calls.append((source, target)) or target,
    )

    launch_gateway(
        checkpoint_path=persistent,
        environment={"VLA_STAGED_CHECKPOINT_PATH": str(staged)},
        execute=lambda _executable, _command, environment: calls.append(environment),
    )

    assert calls[0] == (persistent, staged)
    assert calls[1]["VLA_CHECKPOINT_PATH"] == str(staged)
    assert calls[1]["HF_HUB_OFFLINE"] == "1"


def test_startup_uses_complete_checkpoint_without_hub_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []
    monkeypatch.setattr(
        "vla_pick_and_place.startup.validate_checkpoint_snapshot", lambda _path: None
    )
    monkeypatch.setattr(
        "vla_pick_and_place.startup.cuda_preflight",
        lambda _output: calls.append("cuda"),
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
        "vla_pick_and_place.startup.cuda_preflight",
        lambda _output: calls.append("cuda"),
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


def test_feasibility_startup_preflights_then_runs_once_and_starts_gateway(
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
        execute=lambda executable, command, environment: calls.append(
            ("execute", executable, command, environment)
        ),
    )

    assert calls[0] == ("cuda", output / "cuda-preflight.json")
    assert calls[1][0] == "run"
    assert calls[1][1][-3:] == ["feasibility", "--output", str(output)]
    assert calls[1][2]["check"] is True
    assert "HF_TOKEN" not in calls[1][2]["env"]
    assert calls[1][2]["env"]["KEEP"] == "value"
    assert calls[2][0] == "execute"
    assert calls[2][2][-2:] == ["-m", "vla_pick_and_place.gateway"]
    assert "HF_TOKEN" not in calls[2][3]
    assert read_phase(output) == "gateway_starting"


def test_feasibility_startup_persists_sanitized_subprocess_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkpoint = tmp_path / "checkpoint"
    output = tmp_path / "evidence"
    secret = "hf_paid-secret-value"
    monkeypatch.setattr(
        "vla_pick_and_place.startup.cuda_preflight", lambda _target: None
    )
    monkeypatch.setattr(
        "vla_pick_and_place.startup.validate_checkpoint_snapshot",
        lambda _path: None,
    )

    def fail(_command, **_kwargs):
        raise RuntimeError(f"model load rejected {secret}")

    with pytest.raises(RuntimeError, match="model load rejected"):
        launch_feasibility(
            checkpoint_path=checkpoint,
            output=output,
            environment={"HF_TOKEN": secret},
            run=fail,
            execute=lambda *_args: pytest.fail("gateway must not start"),
        )

    failure = (output / "failure.json").read_text()
    assert secret not in failure
    assert '"stage": "feasibility_subprocess"' in failure


def test_feasibility_startup_replaces_stale_failure_from_previous_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkpoint = tmp_path / "checkpoint"
    output = tmp_path / "evidence"
    output.mkdir()
    (output / "failure.json").write_text('{"message": "stale failure"}\n')
    monkeypatch.setattr(
        "vla_pick_and_place.startup.cuda_preflight", lambda _target: None
    )
    monkeypatch.setattr(
        "vla_pick_and_place.startup.validate_checkpoint_snapshot",
        lambda _path: None,
    )

    with pytest.raises(RuntimeError, match="current failure"):
        launch_feasibility(
            checkpoint_path=checkpoint,
            output=output,
            environment={},
            run=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                RuntimeError("current failure")
            ),
            execute=lambda *_args: pytest.fail("gateway must not start"),
        )

    failure = (output / "failure.json").read_text()
    assert "current failure" in failure
    assert "stale failure" not in failure
