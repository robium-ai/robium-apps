"""Command-line entry point for the quadruped locomotion reference app."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from . import config
from .evidence import collect_manifest, write_manifest


def run_command(cmd: list[str]) -> int:
    print(f"+ (cwd={config.ISAACLAB_ROOT}) {' '.join(cmd)}", flush=True)
    return subprocess.call(cmd, cwd=str(config.ISAACLAB_ROOT))


def doctor() -> int:
    problems: list[str] = []
    launcher = Path(config.ISAACLAB_LAUNCHER)
    if not launcher.is_file():
        problems.append(f"Isaac Lab launcher not found: {launcher}")
    if shutil.which("nvidia-smi") is None:
        problems.append("nvidia-smi is unavailable; run this check on the GPU host")
    else:
        probe = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if probe.returncode:
            problems.append("nvidia-smi could not query the target GPU")
        elif probe.stdout.strip():
            print(f"GPU: {probe.stdout.strip()}")
    if problems:
        for problem in problems:
            print(f"FAIL: {problem}", file=sys.stderr)
        return 1
    print(f"Isaac Lab: {config.ISAACLAB_ROOT}")
    print(f"CLI style: {config.CLI_STYLE}")
    print(f"Task to verify: {config.TASK}")
    print("DOCTOR PASS")
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="check the GPU host and Isaac Lab launcher")
    commands.add_parser("list-envs", help="list task IDs from the installed Isaac Lab")

    train = commands.add_parser("train", help="run a smoke or full training profile")
    train.add_argument("--profile", choices=sorted(config.PROFILES), default="smoke")
    train.add_argument("--video", action="store_true")

    play = commands.add_parser("play", help="play and optionally record a checkpoint")
    play.add_argument("--checkpoint", default="latest")
    play.add_argument("--num-envs", type=int, default=1)
    play.add_argument("--video", action="store_true")

    evidence = commands.add_parser("evidence", help="hash and inventory a run directory or archive")
    evidence.add_argument("source", type=Path)
    evidence.add_argument("--metadata", type=Path)
    evidence.add_argument("--output", type=Path, required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "doctor":
        return doctor()
    if args.command == "list-envs":
        return run_command(config.list_envs_cmd())
    if args.command == "train":
        return run_command(config.train_cmd(args.profile, args.video))
    if args.command == "play":
        return run_command(config.play_cmd(args.checkpoint, args.num_envs, args.video))
    if args.command == "evidence":
        manifest = collect_manifest(args.source, args.metadata)
        write_manifest(manifest, args.output)
        print(f"Wrote {args.output} ({manifest['summary']['files']} files)")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
