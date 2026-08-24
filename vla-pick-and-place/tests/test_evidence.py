import json
from dataclasses import replace
from pathlib import Path

import pytest

from vla_pick_and_place.evidence import (
    EpisodeEvidence,
    build_publication_manifest,
    sha256_file,
    validate_publication_manifest,
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
        dataset_revision="b" * 40,
        application_commit="c" * 40,
        image_digest="sha256:" + "a" * 64,
        gpu="NVIDIA H100 NVL",
        cost_usd=1.25,
    )


def test_publication_manifest_aggregates_simulator_results_and_validates_hashes(
    tmp_path,
):
    episodes = [episode(tmp_path, index, index < 16) for index in range(20)]
    manifest = build(episodes)
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
