import io
import json
import tarfile

from go2_locomotion.evidence import collect_manifest, write_manifest


def test_collects_content_addressed_directory_manifest(tmp_path):
    run = tmp_path / "run"
    (run / "exported").mkdir(parents=True)
    (run / "model_10.pt").write_bytes(b"checkpoint")
    (run / "exported" / "policy.onnx").write_bytes(b"policy")
    metadata = tmp_path / "metadata.json"
    metadata.write_text(json.dumps({"status": "test"}))

    manifest = collect_manifest(run, metadata)
    assert manifest["summary"]["roles"] == {"checkpoint": 1, "policy-export": 1}
    assert manifest["metadata"] == {"status": "test"}
    assert all(len(item["sha256"]) == 64 for item in manifest["files"])


def test_collects_tar_without_extracting(tmp_path):
    archive_path = tmp_path / "run.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        payload = b"video"
        member = tarfile.TarInfo("videos/go2.mp4")
        member.size = len(payload)
        archive.addfile(member, io.BytesIO(payload))

    manifest = collect_manifest(archive_path)
    assert manifest["source"]["kind"] == "archive"
    assert len(manifest["source"]["sha256"]) == 64
    assert manifest["files"][0]["role"] == "rollout"


def test_write_manifest_creates_parent(tmp_path):
    output = tmp_path / "nested" / "manifest.json"
    write_manifest({"ok": True}, output)
    assert json.loads(output.read_text()) == {"ok": True}
