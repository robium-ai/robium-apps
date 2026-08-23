#!/usr/bin/env python3
"""Capture the verified seed-1001 ACT transfer as article media."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from act_aloha_cube_transfer import config
from act_aloha_cube_transfer.checkpoint import ensure_official_checkpoint
from act_aloha_cube_transfer.policy import ACTCheckpoint, preferred_device
from act_aloha_cube_transfer.rollout import run_rollout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default=preferred_device(), choices=("cpu", "mps"))
    parser.add_argument("--seed", type=int, default=1001)
    parser.add_argument("--horizon", type=int, default=100, choices=config.EXECUTION_HORIZONS)
    parser.add_argument("--fps", type=int, default=15)
    parser.add_argument("--output", type=Path, default=Path("assets/gifs/transfer-seed-1001.gif"))
    args = parser.parse_args()

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("ffmpeg is required to encode the article GIF")

    frames: list[Image.Image] = []
    terminal_phase = "reaching"

    def collect(event) -> None:
        nonlocal terminal_phase
        if event.action is not None or event.done:
            frames.append(Image.fromarray(event.frame).convert("RGB"))
        terminal_phase = event.phase

    checkpoint = ACTCheckpoint(ensure_official_checkpoint(), device=args.device)
    result = run_rollout(
        checkpoint,
        seed=args.seed,
        execution_horizon=args.horizon,
        on_step=collect,
    )
    if not result.success or terminal_phase != "transfer complete":
        raise SystemExit(
            f"refusing to publish unsuccessful media: success={result.success}, phase={terminal_phase}"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="act-article-media-") as temporary:
        frame_dir = Path(temporary)
        for index, frame in enumerate(frames):
            frame.save(frame_dir / f"frame-{index:04d}.png", optimize=True)
        subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-framerate",
                str(args.fps),
                "-i",
                str(frame_dir / "frame-%04d.png"),
                "-filter_complex",
                "[0:v]split[x][z];[x]palettegen=max_colors=128:stats_mode=diff[p];"
                "[z][p]paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle",
                str(args.output),
            ],
            check=True,
        )

    metadata = {
        "schema_version": 1,
        "kind": "verified_article_media",
        "checkpoint": {
            "repo_id": config.MODEL_REPO_ID,
            "revision": config.MODEL_REVISION,
        },
        "seed": result.seed,
        "execution_horizon": result.execution_horizon,
        "device": args.device,
        "steps": result.steps,
        "policy_calls": result.policy_calls,
        "success": result.success,
        "terminal_phase": terminal_phase,
        "frames": len(frames),
        "fps": args.fps,
        "duration_seconds": round(len(frames) / args.fps, 3),
        "dimensions": [640, 480],
        "gif_bytes": args.output.stat().st_size,
    }
    metadata_path = args.output.with_suffix(".json")
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps(metadata, indent=2))
    if metadata["duration_seconds"] < 12 or metadata["duration_seconds"] > 18:
        raise SystemExit("article GIF must be 12-18 seconds")
    if metadata["gif_bytes"] >= 8 * 1024 * 1024:
        raise SystemExit("article GIF must be smaller than 8 MiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
