"""Fetch and adapt the official LeRobot PushT checkpoint for LeRobot 0.6."""

from __future__ import annotations

import json
from pathlib import Path

from huggingface_hub import snapshot_download
from lerobot.configs.policies import PreTrainedConfig
from lerobot.datasets.lerobot_dataset import LeRobotDatasetMetadata
from lerobot.policies.factory import make_pre_post_processors

from diffusion_policy_pusht import config


def _required_checkpoint_files() -> tuple[str, ...]:
    return (
        "config.json",
        "model.safetensors",
        "policy_preprocessor.json",
        "policy_postprocessor.json",
    )


def _required_published_files() -> tuple[str, ...]:
    return (
        "README.md",
        "config.json",
        "eval_info.json",
        "model.safetensors",
        "replay.mp4",
        "train_config.json",
    )


def _checkpoint_is_ready(path: Path) -> bool:
    return all((path / name).is_file() for name in _required_checkpoint_files())


def ensure_official_checkpoint() -> Path:
    """Download official weights and create the processor-era compatibility files."""
    path = config.OFFICIAL_CHECKPOINT_DIR
    path.mkdir(parents=True, exist_ok=True)
    if not all((path / name).is_file() for name in _required_published_files()):
        print(
            f"downloading {config.OFFICIAL_MODEL_ID}@{config.OFFICIAL_MODEL_REVISION[:8]}...",
            flush=True,
        )
        snapshot_download(
            repo_id=config.OFFICIAL_MODEL_ID,
            revision=config.OFFICIAL_MODEL_REVISION,
            local_dir=path,
            allow_patterns=(
                "README.md",
                "config.json",
                "eval_info.json",
                "model.safetensors",
                "replay.mp4",
                "train_config.json",
                "training_curves.png",
            ),
        )

    if not (path / "policy_preprocessor.json").is_file():
        print("creating LeRobot 0.6 processor files from lerobot/pusht statistics...", flush=True)
        policy_cfg = PreTrainedConfig.from_pretrained(path)
        if policy_cfg.type != "diffusion":
            raise ValueError(f"official checkpoint type is {policy_cfg.type!r}, expected 'diffusion'")
        policy_cfg.device = "cpu"
        metadata = LeRobotDatasetMetadata(config.DATASET_REPO_ID)
        preprocessor, postprocessor = make_pre_post_processors(
            policy_cfg=policy_cfg,
            dataset_stats=metadata.stats,
        )
        preprocessor.save_pretrained(path)
        postprocessor.save_pretrained(path)

    required = (*_required_published_files(), *_required_checkpoint_files())
    missing = [name for name in required if not (path / name).is_file()]
    if missing:
        raise FileNotFoundError(f"official checkpoint conversion is missing: {', '.join(missing)}")

    provenance = {
        "repo_id": config.OFFICIAL_MODEL_ID,
        "revision": config.OFFICIAL_MODEL_REVISION,
        "training_steps": config.OFFICIAL_TRAINING_STEPS,
        "processor_conversion": {
            "runtime": "lerobot 0.6",
            "dataset_stats": config.DATASET_REPO_ID,
            "weights_modified": False,
        },
    }
    (path / "robium-provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    return path


def _published_metrics(path: Path) -> dict:
    payload = json.loads((path / "eval_info.json").read_text())
    metrics = payload["aggregated"]
    episodes = payload["per_episode"]
    return {
        "n_episodes": len(episodes),
        "n_success": sum(bool(item["success"]) for item in episodes),
        "success_rate": float(metrics["pc_success"]) / 100.0,
        "avg_max_overlap": float(metrics["avg_max_reward"]),
        "avg_sum_reward": float(metrics["avg_sum_reward"]),
        "avg_elapsed_s": float(metrics["eval_ep_s"]),
    }


def _local_experiment() -> dict | None:
    result_path = config.EVAL_OUTPUT_DIR / "5k" / "results.json"
    checkpoint = config.checkpoint_dir(5_000)
    if not result_path.is_file() or not _checkpoint_is_ready(checkpoint):
        return None
    payload = json.loads(result_path.read_text())
    metrics = payload["metrics"]
    video = config.EVAL_OUTPUT_DIR / "5k" / "videos" / f"seed-{config.BENCHMARK_SEEDS[0]}.mp4"
    return {
        "name": "local-5k-experiment",
        "display_name": "Local 5k experiment",
        "training_steps": 5_000,
        "checkpoint": str(checkpoint.relative_to(config.APP_ROOT)),
        "n_action_steps": 8,
        "relationship": "separate configuration; not an earlier rung of the official model",
        "evidence": {
            "kind": "local_partial",
            "complete": bool(payload.get("complete", False)),
            "source": str(result_path.relative_to(config.APP_ROOT)),
            "metrics": {
                "n_episodes": int(metrics["n_episodes"]),
                "n_success": int(metrics["n_success"]),
                "success_rate": float(metrics["success_rate"]),
                "avg_max_overlap": float(metrics["avg_max_coverage"]),
                "avg_sum_reward": float(metrics["avg_sum_reward"]),
                "avg_elapsed_s": float(metrics["avg_elapsed_s"]),
            },
        },
        "videos": [str(video.relative_to(config.APP_ROOT))] if video.is_file() else [],
    }


def build_demo_manifest() -> Path:
    official = ensure_official_checkpoint()
    models = [
        {
            "name": "official-175k",
            "display_name": "Official LeRobot 175k",
            "training_steps": config.OFFICIAL_TRAINING_STEPS,
            "checkpoint": str(official.relative_to(config.APP_ROOT)),
            "n_action_steps": 8,
            "relationship": "official published reference",
            "evidence": {
                "kind": "published",
                "complete": True,
                "source": config.OFFICIAL_MODEL_URL,
                "metrics": _published_metrics(official),
            },
            "videos": [str((official / "replay.mp4").relative_to(config.APP_ROOT))],
        }
    ]
    local = _local_experiment()
    if local is not None:
        models.append(local)

    payload = {
        "schema_version": 3,
        "policy": "diffusion",
        "dataset": config.DATASET_REPO_ID,
        "selected_model": "official-175k",
        "release_success_rate": config.RELEASE_SUCCESS_RATE,
        "inference_modes": {
            "fast": {
                "display_name": "Fast · 10 denoising steps",
                "num_inference_steps": 10,
                "evidence_note": "interactive mode; published metrics do not apply",
            },
            "reference": {
                "display_name": "Reference · 100 denoising steps",
                "num_inference_steps": 100,
                "evidence_note": "matches the official published inference schedule",
            },
        },
        "default_inference_mode": "fast",
        "live_seed": config.BENCHMARK_SEEDS[0],
        "models": models,
    }
    config.DEMO_LADDER_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    config.DEMO_LADDER_MANIFEST.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote {config.DEMO_LADDER_MANIFEST}")
    return config.DEMO_LADDER_MANIFEST


def main() -> int:
    build_demo_manifest()
    return 0
