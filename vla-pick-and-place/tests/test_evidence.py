import json
from argparse import Namespace
from dataclasses import replace
from pathlib import Path

import pytest

from vla_pick_and_place.cli import (
    ensure_fresh_evaluation_output,
    finalize_publication,
    parser,
    record_publication,
)
from vla_pick_and_place.evidence import (
    EpisodeEvidence,
    build_publication_manifest,
    build_publication_pointer,
    sha256_file,
    validate_publication_manifest,
    validate_publication_pointer,
)


def episode(tmp_path: Path, index: int, success: bool) -> EpisodeEvidence:
    video = tmp_path / f"episode-{index}.mp4"
    video.write_bytes(f"video-{index}".encode())
    return EpisodeEvidence(
        episode_index=index,
        state_id=index,
        seed=1000 + index,
        success=success,
        duration_seconds=1.0 + index,
        steps=20 + index,
        action_latency_ms={"mean": 8.0, "p95": 9.0, "max": 10.0},
        video_path=video.name,
        video_sha256=sha256_file(video),
    )


def build(episodes):
    return build_publication_manifest(
        episodes,
        application_commit="c" * 40,
        image_digest="sha256:" + "a" * 64,
        gpu="NVIDIA RTX PRO 4500 Blackwell Server Edition",
        cost_usd=1.25,
    )


def test_publication_manifest_aggregates_simulator_results_and_validates_hashes(
    tmp_path,
):
    episodes = [episode(tmp_path, index, index < 16) for index in range(20)]
    manifest = build(episodes)
    assert manifest["evidence_dataset"]["repo_id"] == (
        "robium/pi05-libero-goal-task-8-evidence"
    )
    assert manifest["result"] == {
        "successes": 16,
        "episodes": 20,
        "target_successes": 16,
        "below_target": False,
    }
    validate_publication_manifest(manifest, artifact_root=tmp_path)


def test_publication_manifest_rejects_zero_partial_duplicate_and_bad_hash(tmp_path):
    with pytest.raises(ValueError, match="exactly 20"):
        build([])

    episodes = [episode(tmp_path, index, True) for index in range(20)]
    duplicate = episodes[:-1] + [replace(episodes[-1], state_id=0)]
    with pytest.raises(ValueError, match="duplicate"):
        build(duplicate)

    manifest = build(episodes)
    manifest["episodes"][0]["video_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="SHA-256"):
        validate_publication_manifest(manifest, artifact_root=tmp_path)


def test_committed_schema_accepts_generated_manifest(tmp_path):
    episodes = [episode(tmp_path, index, index % 2 == 0) for index in range(20)]
    manifest = build(episodes)
    schema = json.loads(
        (Path(__file__).parents[1] / "evidence" / "manifest.schema.json").read_text()
    )
    validate_publication_manifest(manifest, artifact_root=tmp_path, schema=schema)


def test_publication_pointer_pins_final_dataset_revision_and_manifest_hash(tmp_path):
    episodes = [episode(tmp_path, index, index < 16) for index in range(20)]
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(build(episodes), sort_keys=True) + "\n")

    pointer = build_publication_pointer(
        dataset_revision="d" * 40,
        manifest_path=manifest_path,
    )

    assert pointer == {
        "schema_version": "1.0.0",
        "repo_id": "robium/pi05-libero-goal-task-8-evidence",
        "revision": "d" * 40,
        "manifest_sha256": sha256_file(manifest_path),
    }
    validate_publication_pointer(pointer, manifest_path=manifest_path)


def test_publication_pointer_rejects_mutable_revision_and_changed_manifest(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{}\n")
    with pytest.raises(ValueError, match="immutable"):
        build_publication_pointer(
            dataset_revision="main",
            manifest_path=manifest_path,
        )

    pointer = build_publication_pointer(
        dataset_revision="d" * 40,
        manifest_path=manifest_path,
    )
    manifest_path.write_text('{"changed": true}\n')
    with pytest.raises(ValueError, match="SHA-256"):
        validate_publication_pointer(pointer, manifest_path=manifest_path)


def test_evaluation_cli_finalizes_before_recording_immutable_publication_pointer():
    evaluation = parser().parse_args(
        [
            "evaluate",
            "--output",
            "/evidence",
            "--application-commit",
            "c" * 40,
            "--image-digest",
            "sha256:" + "a" * 64,
            "--gpu",
            "NVIDIA RTX PRO 4500 Blackwell Server Edition",
        ]
    )
    assert evaluation.command == "evaluate"
    assert not hasattr(evaluation, "dataset_revision")

    finalization = parser().parse_args(
        ["finalize-publication", "--output", "/evidence", "--cost-usd", "1.25"]
    )
    assert finalization.command == "finalize-publication"

    pointer = parser().parse_args(
        [
            "record-publication",
            "--manifest",
            "/evidence/manifest.json",
            "--dataset-revision",
            "d" * 40,
            "--output",
            "/app/evidence/publication.json",
        ]
    )
    assert pointer.command == "record-publication"


def test_finalize_and_record_publication_commands_write_valid_files(tmp_path):
    run = {
        "application_commit": "c" * 40,
        "image_digest": "sha256:" + "a" * 64,
        "gpu": "NVIDIA RTX PRO 4500 Blackwell Server Edition",
    }
    (tmp_path / "evaluation-run.json").write_text(json.dumps(run) + "\n")
    for index in range(20):
        record = episode(tmp_path, index, index < 16)
        (tmp_path / f"episode-{index}.json").write_text(
            json.dumps(record.__dict__) + "\n"
        )

    assert finalize_publication(Namespace(output=tmp_path, cost_usd=1.25)) == 0
    manifest = tmp_path / "manifest.json"
    pointer_path = tmp_path / "publication.json"
    assert (
        record_publication(
            Namespace(
                manifest=manifest,
                dataset_revision="d" * 40,
                output=pointer_path,
            )
        )
        == 0
    )
    validate_publication_pointer(
        json.loads(pointer_path.read_text()), manifest_path=manifest
    )


def test_evaluation_output_refuses_any_episode_retry_but_allows_diagnostics(tmp_path):
    (tmp_path / "phase.json").write_text("{}\n")
    ensure_fresh_evaluation_output(tmp_path)

    (tmp_path / "episode-0.json").write_text("{}\n")
    with pytest.raises(RuntimeError, match="refusing to retry"):
        ensure_fresh_evaluation_output(tmp_path)
