#!/usr/bin/env python3
"""Resolve pinned shared robotics assets into a verified local directory."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tarfile
import tempfile
import urllib.request
import zipfile

import yaml


SCHEMA_VERSION = "1"
ASSET_ID = re.compile(r"^(world|model|map|recording)\.[a-z0-9][a-z0-9.-]*$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SOURCE_TYPES = {"git-archive", "fuel-world-zip"}
ARCHIVE_TYPES = {"tar.gz", "zip"}
CATALOG_ROOT = Path(__file__).resolve().parent.parent


class AssetError(RuntimeError):
    """A catalog, download, or extraction error suitable for CLI output."""


@dataclass(frozen=True)
class Source:
    type: str
    url: str
    revision: str
    sha256: str
    archive: str
    strip_prefix: str | None


@dataclass(frozen=True)
class Asset:
    id: str
    revision: str
    manifest: Path
    source: Source
    entrypoints: dict[str, str]


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise AssetError(f"{label} must be a mapping")
    return value


def _required_string(data: Mapping[str, object], key: str, label: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AssetError(f"{label}.{key} must be a non-empty string")
    return value


def _load_yaml(path: Path) -> Mapping[str, object]:
    try:
        with path.open(encoding="utf-8") as stream:
            return _mapping(yaml.safe_load(stream), str(path))
    except (OSError, yaml.YAMLError) as exc:
        raise AssetError(f"could not read {path}: {exc}") from exc


def _safe_relative(value: str, label: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise AssetError(f"{label} must stay beneath its asset directory: {value}")
    return path


def _manifest_path(root: Path, value: str) -> Path:
    relative = _safe_relative(value, "catalog manifest")
    candidate = (root / Path(*relative.parts)).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise AssetError(f"catalog manifest escapes the catalog root: {value}")
    return candidate


def _load_manifest(path: Path, expected_id: str) -> Asset:
    data = _load_yaml(path)
    if data.get("schema_version") != SCHEMA_VERSION:
        raise AssetError(f"{path}: unsupported schema_version")
    asset_id = _required_string(data, "id", str(path))
    if asset_id != expected_id or ASSET_ID.fullmatch(asset_id) is None:
        raise AssetError(f"{path}: invalid or mismatched asset id {asset_id!r}")
    if data.get("storage") != "pointer":
        raise AssetError(f"{path}: resolver currently supports pointer assets only")
    revision = _required_string(data, "revision", str(path))

    source_data = _mapping(data.get("source"), f"{path}.source")
    source_type = _required_string(source_data, "type", f"{path}.source")
    archive = _required_string(source_data, "archive", f"{path}.source")
    digest = _required_string(source_data, "sha256", f"{path}.source")
    if source_type not in SOURCE_TYPES:
        raise AssetError(f"{path}: unsupported source type {source_type!r}")
    if archive not in ARCHIVE_TYPES:
        raise AssetError(f"{path}: unsupported archive type {archive!r}")
    if SHA256.fullmatch(digest) is None:
        raise AssetError(f"{path}: source.sha256 must be 64 lowercase hexadecimal characters")
    strip_value = source_data.get("strip_prefix")
    if strip_value is not None and not isinstance(strip_value, str):
        raise AssetError(f"{path}: source.strip_prefix must be a string or null")
    if isinstance(strip_value, str):
        _safe_relative(strip_value, f"{path}.source.strip_prefix")

    entrypoint_data = _mapping(data.get("entrypoints"), f"{path}.entrypoints")
    entrypoints: dict[str, str] = {}
    for name, value in entrypoint_data.items():
        if not isinstance(name, str) or not name or not isinstance(value, str):
            raise AssetError(f"{path}: entrypoints must map names to paths")
        _safe_relative(value, f"{path}.entrypoints.{name}")
        entrypoints[name] = value
    if not entrypoints:
        raise AssetError(f"{path}: at least one entrypoint is required")

    return Asset(
        id=asset_id,
        revision=revision,
        manifest=path,
        source=Source(
            type=source_type,
            url=_required_string(source_data, "url", f"{path}.source"),
            revision=_required_string(source_data, "revision", f"{path}.source"),
            sha256=digest,
            archive=archive,
            strip_prefix=strip_value,
        ),
        entrypoints=entrypoints,
    )


def _load_catalog_file(root: Path, catalog_path: Path) -> dict[str, Asset]:
    data = _load_yaml(catalog_path)
    if data.get("schema_version") != SCHEMA_VERSION:
        raise AssetError(f"{catalog_path}: unsupported schema_version")
    entries = data.get("assets")
    if not isinstance(entries, list):
        raise AssetError(f"{catalog_path}: assets must be a list")

    assets: dict[str, Asset] = {}
    for index, raw_entry in enumerate(entries):
        entry = _mapping(raw_entry, f"{catalog_path}.assets[{index}]")
        asset_id = _required_string(entry, "id", f"{catalog_path}.assets[{index}]")
        if ASSET_ID.fullmatch(asset_id) is None:
            raise AssetError(f"{catalog_path}: invalid asset id {asset_id!r}")
        if asset_id in assets:
            raise AssetError(f"{catalog_path}: duplicate asset id {asset_id}")
        manifest = _manifest_path(
            root, _required_string(entry, "manifest", f"{catalog_path}.assets[{index}]")
        )
        assets[asset_id] = _load_manifest(manifest, asset_id)
    return assets


def load_catalog(root: Path) -> dict[str, Asset]:
    """Load and validate the catalog at root/catalog.yaml."""
    resolved_root = root.resolve()
    return _load_catalog_file(resolved_root, resolved_root / "catalog.yaml")


def _archive_path_safe(name: str) -> bool:
    path = PurePosixPath(name)
    return not path.is_absolute() and bool(path.parts) and ".." not in path.parts


def _extract_tar(archive: Path, destination: Path) -> None:
    with tarfile.open(archive, "r:gz") as bundle:
        members = bundle.getmembers()
        for member in members:
            if not _archive_path_safe(member.name) or member.issym() or member.islnk():
                raise AssetError(f"unsafe tar entry: {member.name}")
        bundle.extractall(destination, members=members, filter="data")


def _extract_zip(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            mode = member.external_attr >> 16
            if not _archive_path_safe(member.filename) or stat.S_ISLNK(mode):
                raise AssetError(f"unsafe zip entry: {member.filename}")
        bundle.extractall(destination)


def _metadata(asset: Asset) -> dict[str, str]:
    return {
        "id": asset.id,
        "manifest_revision": asset.revision,
        "source_revision": asset.source.revision,
        "sha256": asset.source.sha256,
    }


def _entrypoint_paths(asset: Asset, destination: Path) -> dict[str, Path]:
    return {name: destination / Path(*PurePosixPath(value).parts) for name, value in asset.entrypoints.items()}


def _is_cached(asset: Asset, destination: Path) -> bool:
    metadata_path = destination / ".asset.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return metadata == _metadata(asset) and all(
        path.is_file() for path in _entrypoint_paths(asset, destination).values()
    )


def _download(asset: Asset, target: Path) -> None:
    request = urllib.request.Request(asset.source.url, headers={"User-Agent": "robium-assets/1"})
    digest = hashlib.sha256()
    try:
        with urllib.request.urlopen(request) as response, target.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                digest.update(chunk)
                output.write(chunk)
    except OSError as exc:
        raise AssetError(f"download failed for {asset.id}: {exc}") from exc
    actual = digest.hexdigest()
    if actual != asset.source.sha256:
        raise AssetError(
            f"checksum mismatch for {asset.id}: expected {asset.source.sha256}, got {actual}"
        )
    print(f"verified sha256: {actual}")


def _materialize(asset: Asset, destination: Path) -> Path:
    destination = destination.resolve()
    if _is_cached(asset, destination):
        print(f"cached: {asset.id}")
        return destination
    if destination.exists():
        raise AssetError(f"destination exists but is not a verified {asset.id}: {destination}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{asset.id}-", dir=destination.parent) as temporary:
        temporary_path = Path(temporary)
        archive = temporary_path / f"source.{asset.source.archive}"
        extracted = temporary_path / "extracted"
        extracted.mkdir()
        _download(asset, archive)
        if asset.source.archive == "tar.gz":
            _extract_tar(archive, extracted)
        else:
            _extract_zip(archive, extracted)

        source_root = extracted
        if asset.source.strip_prefix is not None:
            source_root = extracted / Path(*PurePosixPath(asset.source.strip_prefix).parts)
            if not source_root.is_dir():
                raise AssetError(f"strip prefix missing for {asset.id}: {asset.source.strip_prefix}")
        materialized = temporary_path / "materialized"
        source_root.rename(materialized)
        missing = [
            name
            for name, path in _entrypoint_paths(asset, materialized).items()
            if not path.is_file()
        ]
        if missing:
            raise AssetError(f"missing entrypoints for {asset.id}: {', '.join(missing)}")
        (materialized / ".asset.json").write_text(
            json.dumps(_metadata(asset), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        materialized.replace(destination)
    return destination


def fetch_asset(
    asset_id: str,
    destination: Path,
    assets: Mapping[str, Asset] | None = None,
) -> Path:
    """Fetch one catalog asset into an exact destination."""
    catalog = load_catalog(CATALOG_ROOT) if assets is None else assets
    try:
        asset = catalog[asset_id]
    except KeyError as exc:
        raise AssetError(f"unknown asset id: {asset_id}") from exc
    return _materialize(asset, destination)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("asset_ids", nargs="*")
    parser.add_argument("--catalog", type=Path, default=CATALOG_ROOT / "catalog.yaml")
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    try:
        catalog_path = args.catalog.resolve()
        assets = _load_catalog_file(catalog_path.parent, catalog_path)
        if args.list:
            if args.asset_ids or args.destination is not None:
                raise AssetError("--list cannot be combined with asset IDs or --destination")
            for asset_id in sorted(assets):
                print(asset_id)
            return 0
        if not args.asset_ids:
            raise AssetError("provide at least one asset ID or use --list")
        if args.destination is not None and len(args.asset_ids) != 1:
            raise AssetError("--destination requires exactly one asset ID")

        for asset_id in args.asset_ids:
            if asset_id not in assets:
                raise AssetError(f"unknown asset id: {asset_id}")
            destination = args.destination
            if destination is None:
                destination = (
                    catalog_path.parent
                    / ".cache"
                    / asset_id
                    / assets[asset_id].source.revision
                )
            resolved = fetch_asset(asset_id, destination, assets)
            for name, path in _entrypoint_paths(assets[asset_id], resolved).items():
                print(f"{name}: {path}")
        return 0
    except AssetError as exc:
        parser.exit(1, f"asset error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
