"""Calibrate inference and benchmark every Diffusion Policy checkpoint."""

from __future__ import annotations

import importlib.metadata
import json
import platform
import shutil
from pathlib import Path
from typing import Callable

import imageio.v2 as imageio
import numpy as np
import torch

from diffusion_policy_pusht import config
from diffusion_policy_pusht.rollout import DiffusionCheckpoint, RolloutStep


def _aggregate(results: list[dict]) -> dict:
    successes = [bool(r["success"]) for r in results]
    return {
        "n_episodes": len(results),
        "n_success": sum(successes),
        "success_rate": float(np.mean(successes)),
        "avg_max_reward": float(np.mean([r["max_reward"] for r in results])),
        "avg_max_coverage": float(np.mean([r["max_coverage"] for r in results])),
        "median_max_coverage": float(np.median([r["max_coverage"] for r in results])),
        "avg_sum_reward": float(np.mean([r["sum_reward"] for r in results])),
        "avg_steps": float(np.mean([r["steps"] for r in results])),
        "avg_elapsed_s": float(np.mean([r["elapsed_s"] for r in results])),
    }


def _evaluate(
    checkpoint: DiffusionCheckpoint,
    seeds: tuple[int, ...],
    *,
    video_path: Path | None = None,
    initial_results: list[dict] | None = None,
    on_episode: Callable[[list[dict]], None] | None = None,
) -> tuple[dict, list[dict]]:
    results = list(initial_results or [])
    completed_seeds = [result["seed"] for result in results]
    if completed_seeds != list(seeds[: len(results)]):
        raise ValueError("saved episode seeds are not a prefix of the requested seed set")
    frames: list[np.ndarray] = []
    first_seed = seeds[0]

    def capture(event: RolloutStep) -> None:
        if not event.done:
            frames.append(event.frame)

    for index in range(len(results), len(seeds)):
        seed = seeds[index]
        print(
            f"episode {index + 1}/{len(seeds)} seed={seed} "
            f"actions={checkpoint.n_action_steps} denoise={checkpoint.num_inference_steps}",
            flush=True,
        )
        result = checkpoint.run(seed=seed, on_step=capture if seed == first_seed else None)
        results.append(result.to_dict())
        if video_path is not None and seed == first_seed:
            video_path.parent.mkdir(parents=True, exist_ok=True)
            imageio.mimsave(video_path, frames, fps=10, macro_block_size=None)
        if on_episode is not None:
            on_episode(results)
    return _aggregate(results), results


def calibrate() -> int:
    path = config.checkpoint_dir(config.CALIBRATION_STEP)
    checkpoint = DiffusionCheckpoint(path, device=config.demo_device())
    config.CALIBRATION_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    candidates: list[dict] = []
    if config.CALIBRATION_RESULTS.is_file():
        previous = json.loads(config.CALIBRATION_RESULTS.read_text())
        if previous.get("checkpoint_step") == config.CALIBRATION_STEP:
            candidates = previous.get("candidates", [])

    def write_partial() -> None:
        payload = {
            "checkpoint_step": config.CALIBRATION_STEP,
            "seeds": list(config.CALIBRATION_SEEDS),
            "complete": False,
            "candidates": candidates,
        }
        config.CALIBRATION_RESULTS.write_text(json.dumps(payload, indent=2) + "\n")

    for n_action_steps in config.CALIBRATION_ACTION_STEPS:
        for num_inference_steps in config.CALIBRATION_INFERENCE_STEPS:
            key = (n_action_steps, num_inference_steps)
            candidate = next(
                (
                    item
                    for item in candidates
                    if (item["n_action_steps"], item["num_inference_steps"]) == key
                ),
                None,
            )
            if candidate is not None and len(candidate.get("episodes", [])) == len(
                config.CALIBRATION_SEEDS
            ):
                print(
                    f"reuse completed candidate actions={n_action_steps} "
                    f"denoise={num_inference_steps}",
                    flush=True,
                )
                continue
            checkpoint.configure(
                n_action_steps=n_action_steps,
                num_inference_steps=num_inference_steps,
            )
            if candidate is None:
                candidate = {
                    "n_action_steps": n_action_steps,
                    "num_inference_steps": num_inference_steps,
                    "episodes": [],
                }
                candidates.append(candidate)

            def persist(episodes: list[dict]) -> None:
                candidate["episodes"] = list(episodes)
                candidate["metrics"] = _aggregate(episodes)
                write_partial()

            metrics, episodes = _evaluate(
                checkpoint,
                config.CALIBRATION_SEEDS,
                initial_results=candidate["episodes"],
                on_episode=persist,
            )
            candidate["metrics"] = metrics
            candidate["episodes"] = episodes
            write_partial()
    selected = max(
        candidates,
        key=lambda c: (
            c["metrics"]["success_rate"],
            c["metrics"]["avg_max_coverage"],
            -c["metrics"]["avg_elapsed_s"],
            -c["n_action_steps"],
            -c["num_inference_steps"],
        ),
    )
    payload = {
        "checkpoint_step": config.CALIBRATION_STEP,
        "seeds": list(config.CALIBRATION_SEEDS),
        "complete": True,
        "candidates": candidates,
        "selected": {
            "n_action_steps": selected["n_action_steps"],
            "num_inference_steps": selected["num_inference_steps"],
            "reason": "highest success_rate, then raw avg_max_coverage, then lower latency",
        },
    }
    out = config.CALIBRATION_RESULTS
    out.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote {out}")
    return 0


def _calibrated_settings() -> dict:
    path = config.CALIBRATION_RESULTS
    if not path.is_file():
        raise FileNotFoundError(f"missing {path}; run `make calibrate` after training to 5k")
    payload = json.loads(path.read_text())
    if payload.get("complete") is False or "selected" not in payload:
        raise RuntimeError(f"incomplete calibration at {path}; rerun `make calibrate` to resume")
    return payload["selected"]


def _checkpoint_entry(step: int, settings: dict) -> dict:
    path = config.checkpoint_dir(step)
    out = config.EVAL_OUTPUT_DIR / f"{step // 1000}k"
    result_path = out / "results.json"
    saved_episodes: list[dict] = []
    if result_path.is_file():
        saved = json.loads(result_path.read_text())
        if saved.get("step") == step and saved.get("inference") == settings:
            saved_episodes = saved.get("episodes", [])
        else:
            shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    checkpoint = DiffusionCheckpoint(path, device=config.demo_device())
    checkpoint.configure(
        n_action_steps=settings["n_action_steps"],
        num_inference_steps=settings["num_inference_steps"],
    )
    video = out / "videos" / f"seed-{config.BENCHMARK_SEEDS[0]}.mp4"

    def persist(episodes: list[dict]) -> None:
        payload = {
            "step": step,
            "inference": settings,
            "complete": False,
            "metrics": _aggregate(episodes),
            "episodes": episodes,
        }
        result_path.write_text(json.dumps(payload, indent=2) + "\n")

    metrics, episodes = _evaluate(
        checkpoint,
        config.BENCHMARK_SEEDS,
        video_path=video,
        initial_results=saved_episodes,
        on_episode=persist,
    )
    if not video.is_file():
        _evaluate(checkpoint, (config.BENCHMARK_SEEDS[0],), video_path=video)
    result_path.write_text(
        json.dumps(
            {
                "step": step,
                "inference": settings,
                "complete": True,
                "metrics": metrics,
                "episodes": episodes,
            },
            indent=2,
        )
        + "\n"
    )
    return {
        "name": f"{step // 1000}k",
        "steps": step,
        "checkpoint": str(path.relative_to(config.APP_ROOT)),
        "metrics": metrics,
        "episodes": episodes,
        "videos": [str(video.relative_to(config.APP_ROOT))],
    }


def eval_ladder() -> int:
    settings = _calibrated_settings()
    steps = config.available_checkpoint_steps()
    if not steps:
        raise FileNotFoundError(f"no retained checkpoints under {config.TRAIN_OUTPUT_DIR}")
    entries = [_checkpoint_entry(step, settings) for step in steps]
    selected = max(
        entries,
        key=lambda r: (
            r["metrics"]["success_rate"],
            r["metrics"]["avg_max_coverage"],
            -r["steps"],
        ),
    )
    manifest = {
        "schema_version": 2,
        "policy": "diffusion",
        "dataset": config.DATASET_REPO_ID,
        "training_seed": config.SEED,
        "benchmark_seeds": list(config.BENCHMARK_SEEDS),
        "release_success_rate": config.RELEASE_SUCCESS_RATE,
        "inference": {
            "n_action_steps": settings["n_action_steps"],
            "num_inference_steps": settings["num_inference_steps"],
        },
        "environment": {
            "platform": platform.platform(),
            "device": config.demo_device(),
            "torch": torch.__version__,
            "lerobot": importlib.metadata.version("lerobot"),
        },
        "selected_rung": selected["name"],
        "selection_reason": "highest success_rate, then raw avg_max_coverage, then earlier checkpoint",
        "release_ready": selected["metrics"]["success_rate"] >= config.RELEASE_SUCCESS_RATE,
        "rungs": entries,
    }
    config.DEMO_LADDER_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    config.DEMO_LADDER_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {config.DEMO_LADDER_MANIFEST}")
    return 0
