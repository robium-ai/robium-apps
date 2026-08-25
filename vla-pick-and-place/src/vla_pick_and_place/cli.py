"""Local fake gates and paid CUDA evaluation commands."""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import time
from dataclasses import asdict
from pathlib import Path

import imageio.v2 as imageio
import numpy as np

from vla_pick_and_place.config import CANONICAL_PROMPT, PUBLICATION_EPISODES
from vla_pick_and_place.diagnostics import write_failure, write_phase
from vla_pick_and_place.evidence import (
    EpisodeEvidence,
    build_publication_manifest,
    build_publication_pointer,
    sha256_file,
    validate_publication_manifest,
    validate_publication_pointer,
)
from vla_pick_and_place.rollout import (
    DeterministicFakePolicy,
    FixtureEnvironment,
    RolloutRunner,
)

APP_ROOT = Path(__file__).parents[2]
FIXTURES = APP_ROOT / "test-assets" / "fixtures"


def _latency_summary(values: tuple[float, ...]) -> dict[str, float]:
    ordered = sorted(values)
    p95_index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95 + 0.999) - 1))
    return {
        "mean": statistics.fmean(ordered),
        "p95": ordered[p95_index],
        "max": ordered[-1],
    }


def doctor() -> int:
    failures = []
    if sys.version_info[:2] != (3, 10):
        failures.append(f"Python 3.10 required, found {platform.python_version()}")
    fixtures = sorted(FIXTURES.glob("*.jpg"))
    if len(fixtures) != 3:
        failures.append("three vendored task-8 fixture frames are required")
    if os.environ.get("VLA_RUNTIME_MODE", "fake") == "real":
        if platform.system() != "Linux":
            failures.append("real mode is supported only in the Linux CUDA image")
        if os.environ.get("MUJOCO_GL") != "egl":
            failures.append("real mode requires MUJOCO_GL=egl")
    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        return 1
    print("DOCTOR PASS: pinned Python, fixtures, and runtime mode are valid")
    return 0


def smoke() -> int:
    frames = []
    runner = RolloutRunner(
        FixtureEnvironment(FIXTURES), DeterministicFakePolicy(), max_steps=10
    )
    result = runner.run(
        0,
        CANONICAL_PROMPT,
        lambda event: frames.append(event.frame) if event.frame else None,
    )
    if (
        not result.success
        or not frames
        or any(frame.getbbox() is None for frame in frames)
    ):
        print("FAKE SMOKE FAIL")
        return 1
    public = asdict(result)
    public.pop("prompt")
    public.pop("action_latency_ms")
    print(json.dumps(public, sort_keys=True))
    print("FAKE SMOKE PASS")
    return 0


def _write_video(path: Path, frames) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with imageio.get_writer(path, fps=20, codec="libx264", quality=7) as writer:
        for frame in frames:
            writer.append_data(np.asarray(frame))


def feasibility(output: Path, *, torch_module=None, runner_factory=None) -> int:
    if torch_module is None:
        import torch as torch_module
    if runner_factory is None:
        from vla_pick_and_place.real import build_real_runner

        runner_factory = build_real_runner
    output.mkdir(parents=True, exist_ok=True)
    try:
        torch_module.cuda.reset_peak_memory_stats()
        write_phase(output, "model_loading")
        started = time.monotonic()
        runner = runner_factory()
        startup_seconds = time.monotonic() - started
        write_phase(output, "rollout")
        frames = []
        result = runner.run(
            0,
            CANONICAL_PROMPT,
            lambda event: frames.append(event.frame) if event.frame else None,
        )
        write_phase(output, "artifact_write")
        video = output / "feasibility.mp4"
        _write_video(video, frames)
        report = {
            "startup_seconds": startup_seconds,
            "peak_vram_bytes": torch_module.cuda.max_memory_allocated(),
            "rollout": {
                **asdict(result),
                "action_latency_ms": _latency_summary(result.action_latency_ms),
            },
            "video": video.name,
            "video_sha256": sha256_file(video),
        }
        report["rollout"].pop("prompt")
        (output / "feasibility.json").write_text(json.dumps(report, indent=2) + "\n")
        write_phase(output, "feasibility_complete", status="completed")
        print(json.dumps(report, sort_keys=True))
        return 0
    except Exception as error:
        write_failure(output, error, environment=os.environ)
        raise


def ensure_fresh_evaluation_output(output: Path) -> None:
    protected = [
        *(output.glob("episode-*.json")),
        *(output.glob("episode-*.mp4")),
        *(output / name for name in ("evaluation-run.json", "manifest.json")),
    ]
    existing = sorted(path.name for path in protected if path.exists())
    if existing:
        raise RuntimeError(
            "evaluation output already contains measured artifacts; refusing to retry: "
            + ", ".join(existing)
        )


def evaluate(args: argparse.Namespace) -> int:
    from vla_pick_and_place.real import build_real_runner

    output: Path = args.output
    output.mkdir(parents=True, exist_ok=True)
    ensure_fresh_evaluation_output(output)
    runner = build_real_runner(execution_profile="compiled")
    episodes = []
    for spec in PUBLICATION_EPISODES:
        frames = []

        def capture(event, target=frames):
            if event.frame:
                target.append(event.frame)

        result = runner.run(
            spec.state_id,
            CANONICAL_PROMPT,
            capture,
        )
        video = output / f"episode-{spec.episode_index}.mp4"
        _write_video(video, frames)
        record = EpisodeEvidence(
            episode_index=spec.episode_index,
            state_id=result.state_id,
            seed=result.seed,
            success=bool(result.success),
            duration_seconds=result.duration_seconds,
            steps=result.steps,
            action_latency_ms=_latency_summary(result.action_latency_ms),
            video_path=video.name,
            video_sha256=sha256_file(video),
        )
        episodes.append(record)
        (output / f"episode-{spec.episode_index}.json").write_text(
            json.dumps(asdict(record), indent=2) + "\n"
        )
    run = {
        "application_commit": args.application_commit,
        "image_digest": args.image_digest,
        "gpu": args.gpu,
    }
    (output / "evaluation-run.json").write_text(json.dumps(run, indent=2) + "\n")
    print(
        json.dumps(
            {
                "episodes": len(episodes),
                "successes": sum(item.success for item in episodes),
            },
            sort_keys=True,
        )
    )
    return 0


def finalize_publication(args: argparse.Namespace) -> int:
    output: Path = args.output
    run = json.loads((output / "evaluation-run.json").read_text())
    records = []
    for index in range(20):
        payload = json.loads((output / f"episode-{index}.json").read_text())
        records.append(EpisodeEvidence(**payload))
    manifest = build_publication_manifest(
        records,
        application_commit=run["application_commit"],
        image_digest=run["image_digest"],
        gpu=run["gpu"],
        cost_usd=args.cost_usd,
    )
    validate_publication_manifest(manifest, artifact_root=output)
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest["result"], sort_keys=True))
    return 0


def record_publication(args: argparse.Namespace) -> int:
    pointer = build_publication_pointer(
        dataset_revision=args.dataset_revision,
        manifest_path=args.manifest,
    )
    validate_publication_pointer(pointer, manifest_path=args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(pointer, indent=2) + "\n")
    print(json.dumps(pointer, sort_keys=True))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor")
    commands.add_parser("smoke")
    feasible = commands.add_parser("feasibility")
    feasible.add_argument("--output", type=Path, required=True)
    evaluation = commands.add_parser("evaluate")
    evaluation.add_argument("--output", type=Path, required=True)
    evaluation.add_argument("--application-commit", required=True)
    evaluation.add_argument("--image-digest", required=True)
    evaluation.add_argument("--gpu", required=True)
    finalization = commands.add_parser("finalize-publication")
    finalization.add_argument("--output", type=Path, required=True)
    finalization.add_argument("--cost-usd", type=float, required=True)
    publication = commands.add_parser("record-publication")
    publication.add_argument("--manifest", type=Path, required=True)
    publication.add_argument("--dataset-revision", required=True)
    publication.add_argument("--output", type=Path, required=True)
    return root


def main() -> None:
    args = parser().parse_args()
    if args.command == "doctor":
        raise SystemExit(doctor())
    if args.command == "smoke":
        raise SystemExit(smoke())
    if args.command == "feasibility":
        raise SystemExit(feasibility(args.output))
    if args.command == "evaluate":
        raise SystemExit(evaluate(args))
    if args.command == "finalize-publication":
        raise SystemExit(finalize_publication(args))
    raise SystemExit(record_publication(args))


if __name__ == "__main__":
    main()
