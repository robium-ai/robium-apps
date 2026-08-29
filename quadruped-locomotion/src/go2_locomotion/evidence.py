"""Create a content-addressed inventory for Isaac Lab run evidence."""

from __future__ import annotations

import hashlib
import json
import tarfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

CHUNK = 1024 * 1024


def _digest(stream: BinaryIO) -> str:
    result = hashlib.sha256()
    while chunk := stream.read(CHUNK):
        result.update(chunk)
    return result.hexdigest()


def _role(name: str) -> str:
    path = Path(name)
    if path.name.startswith("model_") and path.suffix == ".pt":
        return "checkpoint"
    if path.suffix.lower() in {".mp4", ".webm", ".gif"}:
        return "rollout"
    if "exported" in path.parts or path.suffix.lower() == ".onnx":
        return "policy-export"
    if path.suffix.lower() in {".yaml", ".yml", ".json"}:
        return "configuration"
    if path.suffix.lower() in {".log", ".txt", ".csv", ".tfevents"}:
        return "log"
    return "support"


def _directory_files(source: Path) -> list[dict[str, object]]:
    files: list[dict[str, object]] = []
    for path in sorted(item for item in source.rglob("*") if item.is_file()):
        with path.open("rb") as stream:
            digest = _digest(stream)
        files.append(
            {
                "path": path.relative_to(source).as_posix(),
                "role": _role(path.as_posix()),
                "size_bytes": path.stat().st_size,
                "sha256": digest,
            }
        )
    return files


def _archive_files(source: Path) -> list[dict[str, object]]:
    files: list[dict[str, object]] = []
    with tarfile.open(source, "r:*") as archive:
        for member in sorted(archive.getmembers(), key=lambda item: item.name):
            if not member.isfile():
                continue
            stream = archive.extractfile(member)
            if stream is None:
                continue
            with stream:
                digest = _digest(stream)
            files.append(
                {
                    "path": member.name,
                    "role": _role(member.name),
                    "size_bytes": member.size,
                    "sha256": digest,
                }
            )
    return files


def collect_manifest(source: Path, metadata_path: Path | None = None) -> dict[str, object]:
    source = source.resolve()
    if source.is_dir():
        kind = "directory"
        files = _directory_files(source)
        source_digest = None
        source_size = sum(int(item["size_bytes"]) for item in files)
    elif source.is_file() and tarfile.is_tarfile(source):
        kind = "archive"
        files = _archive_files(source)
        with source.open("rb") as stream:
            source_digest = _digest(stream)
        source_size = source.stat().st_size
    else:
        raise ValueError(f"source must be a directory or tar archive: {source}")

    metadata = {}
    if metadata_path:
        metadata = json.loads(metadata_path.read_text())
        if not isinstance(metadata, dict):
            raise ValueError("metadata must contain a JSON object")

    roles = Counter(str(item["role"]) for item in files)
    return {
        "schema_version": 1,
        "app_id": "quadruped-locomotion",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "kind": kind,
            "name": source.name,
            "size_bytes": source_size,
            **({"sha256": source_digest} if source_digest else {}),
        },
        "metadata": metadata,
        "summary": {"files": len(files), "roles": dict(sorted(roles.items()))},
        "files": files,
    }


def write_manifest(manifest: dict[str, object], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2) + "\n")
