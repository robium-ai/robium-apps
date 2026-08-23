from __future__ import annotations

import json
from pathlib import Path

from act_aloha_cube_transfer import config
from act_aloha_cube_transfer.checkpoint import ensure_official_checkpoint
from act_aloha_cube_transfer.policy import ACTCheckpoint, preferred_device
from act_aloha_cube_transfer.rollout import run_rollout

EVIDENCE_PATH = config.APP_ROOT / "outputs/demo/evidence.json"
DEFAULT_SEEDS = tuple(range(1000, 1005))


def published_evidence() -> dict:
    payload = json.loads((config.MODEL_SOURCE_DIR / "eval_info.json").read_text())
    aggregate = payload["aggregated"]
    return {
        "kind": "published",
        "source": f"https://huggingface.co/{config.MODEL_REPO_ID}",
        "revision": config.MODEL_REVISION,
        "episodes": len(payload["per_episode"]),
        "success_rate": float(aggregate["pc_success"]) / 100.0,
        "label": "Official LeRobot evaluation",
    }


def run_calibration(
    *,
    seeds: tuple[int, ...] = DEFAULT_SEEDS,
    device: str | None = None,
    execution_horizon: int = 100,
    output_path: Path = EVIDENCE_PATH,
) -> Path:
    checkpoint = ACTCheckpoint(ensure_official_checkpoint(), device=device or preferred_device())
    records = []
    selected_seed = None
    for seed in seeds:
        result = run_rollout(checkpoint, seed=seed, execution_horizon=execution_horizon)
        record = result.to_dict() | {"device": checkpoint.device}
        records.append(record)
        if selected_seed is None and result.success:
            selected_seed = seed
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "published": published_evidence(),
                    "local": {
                        "kind": "local_calibration",
                        "complete": False,
                        "device": checkpoint.device,
                        "execution_horizon": execution_horizon,
                        "episodes": records,
                    },
                },
                indent=2,
            )
            + "\n"
        )

    replay = None
    if selected_seed is not None:
        replay = run_rollout(
            checkpoint,
            seed=selected_seed,
            execution_horizon=execution_horizon,
        ).to_dict() | {"device": checkpoint.device}
        if not replay["success"]:
            selected_seed = None

    payload = {
        "schema_version": 1,
        "published": published_evidence(),
        "local": {
            "kind": "local_calibration",
            "complete": True,
            "device": checkpoint.device,
            "execution_horizon": execution_horizon,
            "episodes": records,
            "selected_seed": selected_seed,
            "selected_seed_replay": replay,
        },
    }
    output_path.write_text(json.dumps(payload, indent=2) + "\n")
    return output_path
