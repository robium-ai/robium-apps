"""One-time, same-Pod bootstrap for the immutable feasibility checkpoint."""

from __future__ import annotations

import argparse
import hashlib
import os
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from vla_pick_and_place.config import (
    CHECKPOINT_ID,
    CHECKPOINT_MODEL_BYTES,
    CHECKPOINT_MODEL_SHA256,
    CHECKPOINT_REVISION,
    TOKENIZER_FILES,
    TOKENIZER_ID,
    TOKENIZER_REVISION,
)
from vla_pick_and_place.real import (
    CHECKPOINT_ARTIFACT_FILES,
    validate_checkpoint_snapshot,
)

Download = Callable[..., Any]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bootstrap_checkpoint(
    path: Path, *, token: str, download: Download | None = None
) -> None:
    """Download and validate the exact snapshot, marking it valid only last."""
    if not token:
        raise RuntimeError("HF_TOKEN is required for checkpoint bootstrap")
    path.mkdir(parents=True, exist_ok=True)
    revision_file = path / "REVISION"
    pending_revision = path / ".REVISION.pending"
    revision_file.unlink(missing_ok=True)
    pending_revision.unlink(missing_ok=True)
    tokenizer_path = path / "tokenizer"
    tokenizer_revision = tokenizer_path / "REVISION"
    pending_tokenizer_revision = tokenizer_path / ".REVISION.pending"
    tokenizer_revision.unlink(missing_ok=True)
    pending_tokenizer_revision.unlink(missing_ok=True)

    if download is None:
        os.environ["HF_HUB_OFFLINE"] = "0"
        os.environ["TRANSFORMERS_OFFLINE"] = "0"
        from huggingface_hub import snapshot_download

        download = snapshot_download

    download(
        repo_id=CHECKPOINT_ID,
        revision=CHECKPOINT_REVISION,
        local_dir=path,
        allow_patterns=list(CHECKPOINT_ARTIFACT_FILES),
        token=token,
    )
    download(
        repo_id=TOKENIZER_ID,
        revision=TOKENIZER_REVISION,
        local_dir=tokenizer_path,
        allow_patterns=list(TOKENIZER_FILES),
        token=token,
    )

    downloaded_files = (
        *CHECKPOINT_ARTIFACT_FILES,
        *(f"tokenizer/{name}" for name in TOKENIZER_FILES),
    )
    missing = [name for name in downloaded_files if not (path / name).is_file()]
    if missing:
        raise RuntimeError(f"checkpoint snapshot is incomplete: {', '.join(missing)}")
    model = path / "model.safetensors"
    if model.stat().st_size != CHECKPOINT_MODEL_BYTES:
        raise RuntimeError(
            f"model byte size mismatch: expected {CHECKPOINT_MODEL_BYTES}, "
            f"found {model.stat().st_size}"
        )
    actual_hash = _sha256(model)
    if actual_hash != CHECKPOINT_MODEL_SHA256:
        raise RuntimeError(
            f"model SHA-256 mismatch: expected {CHECKPOINT_MODEL_SHA256}, "
            f"found {actual_hash}"
        )

    pending_tokenizer_revision.parent.mkdir(parents=True, exist_ok=True)
    pending_tokenizer_revision.write_text(f"{TOKENIZER_REVISION}\n")
    pending_tokenizer_revision.replace(tokenizer_revision)
    pending_revision.write_text(f"{CHECKPOINT_REVISION}\n")
    pending_revision.replace(revision_file)
    validate_checkpoint_snapshot(path)


def offline_environment(source: Mapping[str, str]) -> dict[str, str]:
    """Return a child environment with Hub credentials removed and offline set."""
    result = dict(source)
    result.pop("HF_TOKEN", None)
    result["HF_HUB_OFFLINE"] = "1"
    result["TRANSFORMERS_OFFLINE"] = "1"
    return result


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    root.add_argument(
        "--checkpoint-path",
        type=Path,
        default=Path(os.environ.get("VLA_CHECKPOINT_PATH", "/models/pi05-libero-v044")),
    )
    root.add_argument("command", nargs=argparse.REMAINDER)
    return root


def main(argv: Sequence[str] | None = None) -> None:
    args = parser().parse_args(argv)
    token = os.environ.get("HF_TOKEN", "")
    bootstrap_checkpoint(args.checkpoint_path, token=token)
    print("CHECKPOINT BOOTSTRAP READY", flush=True)
    command = list(args.command)
    if command and command[0] == "--":
        command.pop(0)
    if command:
        os.execvpe(command[0], command, offline_environment(os.environ))


if __name__ == "__main__":
    main()
