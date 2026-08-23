"""Download, migrate, and verify the pinned official ACT checkpoint."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import lerobot
from huggingface_hub import snapshot_download

from act_aloha_cube_transfer import config

SOURCE_FILES = (
    "README.md",
    "config.json",
    "eval_info.json",
    "model.safetensors",
    "train_config.json",
)
MIGRATED_FILES = (
    "config.json",
    "model.safetensors",
    "policy_preprocessor.json",
    "policy_postprocessor.json",
)
MIGRATION_VERSION = 1


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _hashes(root: Path, names: tuple[str, ...]) -> dict[str, str]:
    return {name: _sha256(root / name) for name in names}


def _manifest_is_ready(path: Path) -> bool:
    manifest_path = path / "manifest.json"
    if not manifest_path.is_file():
        return False
    try:
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("status") != "ready":
            return False
        if manifest.get("repo_id") != config.MODEL_REPO_ID:
            return False
        if manifest.get("revision") != config.MODEL_REVISION:
            return False
        for name, expected in manifest["migrated_files"].items():
            candidate = path / name
            if not candidate.is_file() or _sha256(candidate) != expected:
                return False
    except (KeyError, OSError, ValueError, json.JSONDecodeError):
        return False
    return all((path / name).is_file() for name in MIGRATED_FILES)


def _download_source() -> Path:
    source = config.MODEL_SOURCE_DIR
    source.mkdir(parents=True, exist_ok=True)
    if not all((source / name).is_file() for name in SOURCE_FILES):
        print(
            f"downloading {config.MODEL_REPO_ID}@{config.MODEL_REVISION[:8]}...",
            flush=True,
        )
        snapshot_download(
            repo_id=config.MODEL_REPO_ID,
            revision=config.MODEL_REVISION,
            local_dir=source,
            allow_patterns=SOURCE_FILES,
        )
    missing = [name for name in SOURCE_FILES if not (source / name).is_file()]
    if missing:
        raise FileNotFoundError(f"source checkpoint is missing: {', '.join(missing)}")
    return source


def ensure_official_checkpoint() -> Path:
    """Return an auditable processor-era copy of the official checkpoint."""
    destination = config.MODEL_DIR
    if _manifest_is_ready(destination):
        return destination

    source = _download_source()
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="act-migration-", dir=destination.parent))
    try:
        command = [
            sys.executable,
            "-m",
            "lerobot.processor.migrate_policy_normalization",
            "--pretrained-path",
            str(source),
            "--output-dir",
            str(staging),
        ]
        print("migrating legacy normalization with LeRobot's official tool...", flush=True)
        subprocess.run(command, check=True)

        missing = [name for name in MIGRATED_FILES if not (staging / name).is_file()]
        if missing:
            raise FileNotFoundError(f"migration output is missing: {', '.join(missing)}")

        policy_config = json.loads((staging / "config.json").read_text())
        if policy_config.get("type") != "act":
            raise ValueError(f"migrated checkpoint type is {policy_config.get('type')!r}, expected 'act'")
        if policy_config.get("chunk_size") != config.ACTION_CHUNK_SIZE:
            raise ValueError("migrated checkpoint does not preserve the 100-action ACT chunk")

        manifest = {
            "status": "ready",
            "repo_id": config.MODEL_REPO_ID,
            "revision": config.MODEL_REVISION,
            "migration": {
                "version": MIGRATION_VERSION,
                "implementation": "lerobot.processor.migrate_policy_normalization",
                "lerobot_version": lerobot.__version__,
                "source_modified": False,
            },
            "contract": {
                "camera": "observation.images.top",
                "camera_shape": [3, 480, 640],
                "state_shape": [14],
                "action_shape": [14],
                "chunk_size": config.ACTION_CHUNK_SIZE,
            },
            "source_files": _hashes(source, SOURCE_FILES),
            "migrated_files": _hashes(staging, MIGRATED_FILES),
        }
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

        if destination.exists():
            shutil.rmtree(destination)
        os.replace(staging, destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    if not _manifest_is_ready(destination):
        raise ValueError("migrated checkpoint failed its manifest verification")
    return destination
