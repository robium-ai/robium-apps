from __future__ import annotations

import argparse
import json
from pathlib import Path

from .runtime import (
    MODEL_FILENAME,
    MODEL_REPO,
    MODEL_REVISION,
    MODEL_SHA256,
    cached_checkpoint,
    fetch_checkpoint,
    run_check,
    run_episode,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a pretrained PPO CarRacing policy")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("download", help="fetch and verify the pinned checkpoint")
    subparsers.add_parser("status", help="show whether the pinned checkpoint is cached")

    run_parser = subparsers.add_parser("run", help="open a visible autonomous rollout")
    run_parser.add_argument("--seed", type=int, default=1)
    run_parser.add_argument("--max-policy-steps", type=int)

    check_parser = subparsers.add_parser("check", help="measure headless seeded episodes")
    check_parser.add_argument("--episodes", type=int, default=3)
    check_parser.add_argument("--seed", type=int, default=0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "download":
        checkpoint = fetch_checkpoint()
        print(f"MODEL READY: {checkpoint}")
        print(f"sha256: {MODEL_SHA256}")
        return 0

    if args.command == "status":
        checkpoint = cached_checkpoint()
        if checkpoint:
            size_mb = Path(checkpoint).stat().st_size / 1_000_000
            print(f"ok: pinned checkpoint cached ({size_mb:.1f} MB)")
            return 0
        print("note: pinned checkpoint not cached; './app build' will download it")
        return 0

    if args.command == "run":
        print(f"Loading {MODEL_REPO}@{MODEL_REVISION[:8]} ({MODEL_FILENAME})")
        result = run_episode(
            seed=args.seed,
            render=True,
            max_policy_steps=args.max_policy_steps,
        )
        print(json.dumps(result.__dict__, indent=2))
        return 0

    if args.episodes < 1:
        raise SystemExit("--episodes must be at least 1")
    evidence = run_check(episodes=args.episodes, first_seed=args.seed)
    print(json.dumps(evidence, indent=2))
    print("CHECK COMPLETE: outputs/last-check.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
