"""Construction and strict validation of the 20-episode publication manifest."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import jsonschema

from vla_pick_and_place.config import (
    BATCH_SIZE,
    CANONICAL_PROMPT,
    CHECKPOINT_ID,
    CHECKPOINT_REVISION,
    LEROBOT_REVISION,
    LIBERO_REVISION,
    MAX_STEPS,
    N_ACTION_STEPS,
    TASK_ID,
    TASK_NAME,
    TASK_SUITE,
)


@dataclass(frozen=True)
class EpisodeEvidence:
    episode_index: int
    state_id: int
    seed: int
    success: bool
    duration_seconds: float
    steps: int
    action_latency_ms: dict[str, float]
    video_path: str
    video_sha256: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_git_revision(value: str) -> bool:
    return len(value) == 40 and all(
        character in "0123456789abcdef" for character in value
    )


def build_publication_manifest(
    episodes: list[EpisodeEvidence],
    *,
    dataset_revision: str,
    application_commit: str,
    image_digest: str,
    gpu: str,
    cost_usd: float,
) -> dict[str, Any]:
    if len(episodes) != 20:
        raise ValueError("publication evidence must contain exactly 20 episodes")
    episode_ids = [episode.episode_index for episode in episodes]
    state_ids = [episode.state_id for episode in episodes]
    if len(set(episode_ids)) != 20 or len(set(state_ids)) != 20:
        raise ValueError("duplicate episode_index or state_id")
    expected = list(range(20))
    if sorted(episode_ids) != expected or sorted(state_ids) != expected:
        raise ValueError("publication episode and state IDs must each be 0 through 19")
    for episode in episodes:
        if episode.seed != 1000 + episode.state_id:
            raise ValueError("state-to-seed configuration drift")

    successes = sum(episode.success for episode in episodes)
    return {
        "schema_version": "1.0.0",
        "evidence_dataset": {
            "repo_id": "robium-ai/pi05-libero-goal-task-8-evidence",
            "revision": dataset_revision,
        },
        "result": {
            "successes": successes,
            "episodes": 20,
            "target_successes": 16,
            "below_target": successes < 16,
        },
        "benchmark": {
            "suite": TASK_SUITE,
            "task_id": TASK_ID,
            "task_name": TASK_NAME,
            "prompt": CANONICAL_PROMPT,
            "prompt_class": "benchmark-supported",
            "batch_size": BATCH_SIZE,
            "max_steps": MAX_STEPS,
            "n_action_steps": N_ACTION_STEPS,
        },
        "revisions": {
            "checkpoint_id": CHECKPOINT_ID,
            "checkpoint": CHECKPOINT_REVISION,
            "lerobot": LEROBOT_REVISION,
            "libero": LIBERO_REVISION,
            "application": application_commit,
            "image": image_digest,
        },
        "compute": {"gpu": gpu, "runpod_cost_usd": cost_usd},
        "episodes": [
            asdict(episode)
            for episode in sorted(episodes, key=lambda item: item.episode_index)
        ],
        "reproduce": {
            "command": "python -m vla_pick_and_place.cli evaluate --output /evidence",
            "state_ids": expected,
            "seeds": [1000 + index for index in expected],
        },
    }


def validate_publication_manifest(
    manifest: dict[str, Any],
    *,
    artifact_root: Path,
    schema: dict[str, Any] | None = None,
) -> None:
    if schema is None:
        schema_path = Path(__file__).parents[2] / "evidence" / "manifest.schema.json"
        import json

        schema = json.loads(schema_path.read_text())
    jsonschema.validate(manifest, schema)
    if manifest["result"]["episodes"] != 20 or len(manifest["episodes"]) != 20:
        raise ValueError("publication evidence must contain exactly 20 episodes")
    successes = sum(bool(episode["success"]) for episode in manifest["episodes"])
    if successes != manifest["result"]["successes"]:
        raise ValueError("aggregate success count does not match episode results")
    if manifest["result"]["below_target"] != (
        successes < manifest["result"]["target_successes"]
    ):
        raise ValueError("below-target flag does not match aggregate result")
    ids = [episode["episode_index"] for episode in manifest["episodes"]]
    states = [episode["state_id"] for episode in manifest["episodes"]]
    if len(set(ids)) != 20 or len(set(states)) != 20:
        raise ValueError("duplicate episode_index or state_id")
    for key in ("checkpoint", "lerobot", "libero", "application"):
        if not _is_git_revision(manifest["revisions"][key]):
            raise ValueError(f"{key} must be an immutable 40-character revision")
    if not _is_git_revision(manifest["evidence_dataset"]["revision"]):
        raise ValueError("evidence dataset must use an immutable revision")
    for episode in manifest["episodes"]:
        if episode["seed"] != 1000 + episode["state_id"]:
            raise ValueError("state-to-seed configuration drift")
        actual = sha256_file(artifact_root / episode["video_path"])
        if actual != episode["video_sha256"]:
            raise ValueError(f"video SHA-256 mismatch: {episode['video_path']}")
