from __future__ import annotations

from contextlib import nullcontext
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile
import zipfile

import pytest
import yaml


ASSETS = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "robium_fetch_assets", ASSETS / "scripts" / "fetch_assets.py"
)
assert SPEC and SPEC.loader
fetch_assets = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = fetch_assets
SPEC.loader.exec_module(fetch_assets)


def archive_bytes(kind: str, entrypoint: str, content: bytes = b"world") -> bytes:
    stream = io.BytesIO()
    if kind == "tar.gz":
        with tarfile.open(fileobj=stream, mode="w:gz") as bundle:
            info = tarfile.TarInfo(f"source/{entrypoint}")
            info.size = len(content)
            bundle.addfile(info, io.BytesIO(content))
    else:
        with zipfile.ZipFile(stream, mode="w") as bundle:
            bundle.writestr(entrypoint, content)
    return stream.getvalue()


def write_catalog(root: Path, *, archive: str, payload: bytes, license_file: bool = True) -> None:
    asset_dir = root / "worlds" / "fixture"
    asset_dir.mkdir(parents=True)
    if license_file:
        (asset_dir / "LICENSE").write_text("fixture license\n", encoding="utf-8")
    (root / "catalog.yaml").write_text(yaml.safe_dump({
        "schema_version": "1",
        "assets": [{
            "id": "world.fixture",
            "kind": "world",
            "name": "Fixture World",
            "storage": "pointer",
            "manifest": "worlds/fixture/asset.yaml",
        }],
    }), encoding="utf-8")
    (asset_dir / "asset.yaml").write_text(yaml.safe_dump({
        "schema_version": "1",
        "id": "world.fixture",
        "kind": "world",
        "name": "Fixture World",
        "revision": "1",
        "storage": "pointer",
        "license": {"id": "MIT", "file": "LICENSE"},
        "verification": {"date": "2026-08-27", "method": "fixture clean-cache fetch"},
        "source": {
            "type": "git-archive" if archive == "tar.gz" else "fuel-world-zip",
            "repository": "https://example.test/world.fixture",
            "revision": "abc123" if archive == "tar.gz" else "2",
            "url": "https://example.test/world.fixture/archive",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "archive": archive,
            "strip_prefix": "source" if archive == "tar.gz" else None,
        },
        "entrypoints": {"world": "world.sdf"},
    }), encoding="utf-8")


def test_live_catalog_has_complete_provenance_and_license_files():
    assets = fetch_assets.load_catalog(ASSETS)
    assert set(assets) == {"world.aws-small-house", "world.tugbot-warehouse"}
    for asset in assets.values():
        assert asset.name in {"AWS RoboMaker Small House", "Tugbot in Warehouse"}
        assert asset.source.repository.startswith("https://")
        assert asset.source.revision
        assert len(asset.source.sha256) == 64
        assert asset.license.id
        assert asset.license.file.is_file()
        assert asset.verification.date == "2026-08-27"
        assert "clean-cache" in asset.verification.method.lower()
        assert asset.entrypoints


@pytest.mark.parametrize("archive", ["tar.gz", "zip"])
def test_clean_fetch_verifies_digest_extracts_entrypoint_and_writes_metadata(tmp_path, monkeypatch, archive):
    payload = archive_bytes(archive, "world.sdf")
    root = tmp_path / "catalog"
    write_catalog(root, archive=archive, payload=payload)
    asset = fetch_assets.load_catalog(root)["world.fixture"]
    monkeypatch.setattr(fetch_assets.urllib.request, "urlopen", lambda request: nullcontext(io.BytesIO(payload)))

    destination = tmp_path / "cache" / "fixture"
    assert fetch_assets.fetch_asset("world.fixture", destination, {asset.id: asset}) == destination.resolve()
    assert (destination / "world.sdf").read_bytes() == b"world"
    metadata = json.loads((destination / ".asset.json").read_text(encoding="utf-8"))
    assert metadata == fetch_assets._metadata(asset)


def test_checksum_mismatch_leaves_no_materialized_destination(tmp_path, monkeypatch):
    expected = archive_bytes("zip", "world.sdf")
    root = tmp_path / "catalog"
    write_catalog(root, archive="zip", payload=expected)
    asset = fetch_assets.load_catalog(root)["world.fixture"]
    monkeypatch.setattr(
        fetch_assets.urllib.request,
        "urlopen",
        lambda request: nullcontext(io.BytesIO(b"not the pinned archive")),
    )
    destination = tmp_path / "cache" / "fixture"

    with pytest.raises(fetch_assets.AssetError, match="checksum mismatch"):
        fetch_assets.fetch_asset("world.fixture", destination, {asset.id: asset})
    assert not destination.exists()


def test_catalog_rejects_missing_license_evidence(tmp_path):
    payload = archive_bytes("zip", "world.sdf")
    root = tmp_path / "catalog"
    write_catalog(root, archive="zip", payload=payload, license_file=False)
    with pytest.raises(fetch_assets.AssetError, match="license file does not exist"):
        fetch_assets.load_catalog(root)
