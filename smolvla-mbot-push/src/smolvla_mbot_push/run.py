"""Command-line surface.

Everything runs in simulation: drive the arena by hand, or step it headlessly to
check it still works.
"""

from __future__ import annotations

import argparse
import time

import numpy as np

from .config import CONTROL_HZ
from .sim import PushEnv


def cmd_check(args: argparse.Namespace) -> int:
    """Headless self-check: no controller, no window, just step and render."""
    with PushEnv(render_size=args.render_size, seed=args.seed) as env:
        frame = env.reset(seed=args.seed)
        rng = np.random.default_rng(args.seed)
        for _ in range(args.steps):
            frame = env.step(rng.uniform(-1, 1, size=2))
        print(f"ok: {args.steps} steps, frame {frame.shape} {frame.dtype}")
        print(f"    robot {env.body_xy('chassis').round(3).tolist()}")
        print(f"    block {env.body_xy('block').round(3).tolist()}")
    return 0


def cmd_drive(args: argparse.Namespace) -> int:
    """Drive the arena by hand, watching the overhead view."""
    from .ui import Teleop, Viewer

    import pygame

    viewer = Viewer(size=args.window)
    teleop = Teleop()
    period = 1.0 / CONTROL_HZ

    print(f"Driving with {teleop.source}.")
    print("q quits, r resets the layout.")

    with PushEnv(render_size=args.render_size, seed=args.seed) as env:
        frame = env.reset()
        running = True
        try:
            while running:
                started = time.monotonic()

                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False
                    elif event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_q:
                            running = False
                        elif event.key == pygame.K_r:
                            frame = env.reset()

                action = teleop.read(period)
                frame = env.step(action)
                viewer.show(
                    frame,
                    [
                        f"throttle {action[0]:+0.2f}   steer {action[1]:+0.2f}",
                        teleop.source,
                    ],
                )

                elapsed = time.monotonic() - started
                if elapsed < period:
                    time.sleep(period - elapsed)
        except KeyboardInterrupt:
            pass
        finally:
            teleop.close()
            viewer.close()
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    """Record teleoperated episodes into a LeRobotDataset."""
    from pathlib import Path

    from .record import RecordConfig, record

    root = Path(args.root) if args.root else Path("outputs/datasets") / args.repo_id.split("/")[-1]
    return record(
        RecordConfig(
            repo_id=args.repo_id,
            root=root,
            episodes=args.episodes,
            render_size=args.render_size,
            window=args.window,
            push_to_hub=args.push_to_hub,
            private=args.private,
            resume=args.resume,
        )
    )


def cmd_push(args: argparse.Namespace) -> int:
    """Upload an already-recorded dataset to the Hub."""
    from pathlib import Path

    from .record import push

    root = Path(args.root) if args.root else Path("outputs/datasets") / args.repo_id.split("/")[-1]
    return push(args.repo_id, root, private=args.private)


def cmd_rollout(args: argparse.Namespace) -> int:
    """Run a trained checkpoint in the arena."""
    from pathlib import Path

    from .rollout import RolloutConfig, rollout

    return rollout(
        RolloutConfig(
            policy_path=args.policy,
            dataset_repo_id=args.repo_id,
            dataset_root=Path(args.root) if args.root else None,
            episodes=args.episodes,
            steps=args.steps,
            render_size=args.render_size,
            window=args.window,
            device=args.device,
            seed=args.seed if args.seed is not None else 1000,
            show=not args.no_window,
            video_path=Path(args.save_video) if args.save_video else None,
            realtime=args.realtime,
            latency_ms=args.latency_ms,
            stop_and_go=args.stop_and_go,
            settle_seconds=args.settle,
            n_action_steps=args.n_action_steps,
        )
    )


def cmd_interactive(args: argparse.Namespace) -> int:
    """Set the scene by hand, then run the policy on it."""
    from pathlib import Path

    from .interactive import InteractiveConfig, interactive

    return interactive(
        InteractiveConfig(
            policy_path=args.policy,
            dataset_repo_id=args.repo_id,
            dataset_root=Path(args.root) if args.root else None,
            render_size=args.render_size,
            window=args.window,
            device=args.device,
            seed=args.seed,
            realtime=args.realtime,
            latency_ms=args.latency_ms,
            stop_and_go=args.stop_and_go,
            settle_seconds=args.settle,
            n_action_steps=args.n_action_steps,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="smolvla-mbot-push",
        description="A differential-drive robot pushing a block, seen from overhead.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--render-size", type=int, default=256, help="Observation size")
        p.add_argument("--seed", type=int, default=None)

    check = sub.add_parser("check", help="Headless: step and render the arena")
    common(check)
    check.add_argument("--steps", type=int, default=50)
    check.set_defaults(func=cmd_check)

    drive = sub.add_parser("drive", help="Drive the arena with a game controller")
    common(drive)
    drive.add_argument("--window", type=int, default=640, help="Preview window size")
    drive.set_defaults(func=cmd_drive)

    rec = sub.add_parser("record", help="Record teleoperated episodes to a dataset")
    common(rec)
    rec.add_argument("--repo-id", required=True, help="Hub dataset id, e.g. robium/mbot-push-sim")
    rec.add_argument("--episodes", type=int, default=5)
    rec.add_argument("--root", help="Local dataset directory (default: outputs/datasets/<name>)")
    rec.add_argument("--window", type=int, default=640)
    rec.add_argument("--push-to-hub", action="store_true", help="Upload when finished")
    rec.add_argument("--private", action="store_true", help="Upload as a private dataset")
    rec.add_argument("--resume", action="store_true", help="Append to an existing dataset")
    rec.set_defaults(func=cmd_record)

    push_p = sub.add_parser("push", help="Upload a recorded dataset to the Hub")
    push_p.add_argument("--repo-id", required=True)
    push_p.add_argument("--root", help="Local dataset directory")
    push_p.add_argument("--private", action="store_true")
    push_p.set_defaults(func=cmd_push)

    roll = sub.add_parser("rollout", help="Run a trained checkpoint in the arena")
    common(roll)
    roll.add_argument("--policy", required=True, help="Checkpoint dir or Hub model id")
    roll.add_argument("--repo-id", required=True, help="Dataset the policy was trained on")
    roll.add_argument("--root", help="Local dataset directory")
    roll.add_argument("--episodes", type=int, default=5)
    roll.add_argument("--steps", type=int, default=300)
    roll.add_argument("--window", type=int, default=640)
    roll.add_argument("--device", default="mps", help="mps, cpu, or cuda")
    roll.add_argument("--no-window", action="store_true")
    roll.add_argument("--save-video", help="Write the rollout to an mp4, e.g. outputs/rollout.mp4")
    roll.add_argument(
        "--realtime",
        action="store_true",
        help="Let the arena keep moving while the policy thinks, the way it "
        "does on hardware. MuJoCo otherwise pauses during inference, which "
        "hands a slow policy a frame that is still true when its chunk lands",
    )
    roll.add_argument(
        "--latency-ms",
        type=float,
        metavar="MS",
        help="Charge this per forward pass instead of the measured cost. Lets a "
        "latency be swept, or one this machine does not have be reproduced",
    )
    roll.add_argument(
        "--stop-and-go",
        action="store_true",
        help="Drive a chunk, halt, settle, then look and plan again - matching "
        "the hardware flag of the same name. The clock keeps running through "
        "the halt, so the robot stops but the world does not",
    )
    roll.add_argument(
        "--settle",
        type=float,
        default=0.5,
        metavar="S",
        help="Seconds halted before looking (default 0.5)",
    )
    roll.add_argument(
        "--n-action-steps",
        type=int,
        metavar="N",
        help="Actions to execute per chunk before looking again (default: the "
        "value the checkpoint trained with). Cannot exceed chunk_size",
    )
    roll.set_defaults(func=cmd_rollout)

    inter = sub.add_parser("interactive", help="Place things by hand, then run the policy")
    common(inter)
    inter.add_argument(
        "--realtime",
        action="store_true",
        help="Let the arena keep moving while the policy thinks, as hardware does",
    )
    inter.add_argument(
        "--latency-ms",
        type=float,
        metavar="MS",
        help="Charge this per forward pass instead of the measured cost",
    )
    inter.add_argument(
        "--stop-and-go",
        action="store_true",
        help="Drive a chunk, halt, settle, then look and plan again",
    )
    inter.add_argument("--settle", type=float, default=0.5, metavar="S",
                       help="Seconds halted before looking (default 0.5)")
    inter.add_argument(
        "--n-action-steps",
        type=int,
        metavar="N",
        help="Actions to execute per chunk before looking again (default: the "
        "value the checkpoint trained with). Cannot exceed chunk_size",
    )
    inter.add_argument("--policy", required=True, help="Checkpoint dir or Hub model id")
    inter.add_argument("--repo-id", required=True, help="Dataset the policy was trained on")
    inter.add_argument("--root", help="Local dataset directory")
    inter.add_argument("--window", type=int, default=700)
    inter.add_argument("--device", default="mps", help="mps, cpu, or cuda")
    inter.set_defaults(func=cmd_interactive)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
