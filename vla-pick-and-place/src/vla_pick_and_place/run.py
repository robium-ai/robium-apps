"""CLI dispatcher: python -m vla_pick_and_place.run <subcommand>.

Every subcommand here is something a person can run and read the output of,
because each one is also the evidence behind a claim the app makes:

  contract       what the pinned environment actually is
  dataset-check  whether a pinned dataset matches that environment
  controllers    which controllers may run, and why the rest may not
  expert         measure the scripted expert's success rate
  record N       record N successful expert demonstrations as a LeRobot dataset
  sim            drive the simulator headless and write an .rrd
  play           replay a published episode headless and write an .rrd
"""

import json
import sys


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(__doc__.strip(), file=sys.stderr)
        return 2

    cmd, *rest = argv

    if cmd == "contract":
        from vla_pick_and_place.config import CONTRACT_JSON
        from vla_pick_and_place.env import contract

        measured = contract.capture()
        problems = contract.diff(measured)
        CONTRACT_JSON.parent.mkdir(parents=True, exist_ok=True)
        CONTRACT_JSON.write_text(json.dumps(measured, indent=2) + "\n")
        _print(measured)
        print(f"\nwritten to {CONTRACT_JSON}", file=sys.stderr)
        if problems:
            print("\nCONTRACT MISMATCH:", file=sys.stderr)
            for p in problems:
                print(f"  - {p}", file=sys.stderr)
            return 1
        print("CONTRACT OK", file=sys.stderr)
        return 0

    if cmd == "dataset-check":
        from vla_pick_and_place.config import OBS_OVERHEAD, OBS_WRIST
        from vla_pick_and_place.data import datasets
        from vla_pick_and_place.env.nexus import NexusPickAndPlace

        # A live reset frame is what makes this a scene check and not just a
        # schema check — see data/datasets.py.
        with NexusPickAndPlace() as env:
            obs, _ = env.reset(seed=0)
            reference = {OBS_WRIST: obs[OBS_WRIST], OBS_OVERHEAD: obs[OBS_OVERHEAD]}

        pins = (
            [datasets.REGISTRY[rest[0]]] if rest else [datasets.PRIMARY, datasets.ALTERNATE]
        )
        failed = False
        for pin in pins:
            result = datasets.verify(pin, reference_frames=reference)
            _print(
                {
                    "repo_id": pin.repo_id,
                    "revision": pin.revision,
                    "role": "primary" if pin is datasets.PRIMARY else "second candidate",
                    "schema_ok": result.schema_ok,
                    "scene_ok": result.scene_ok,
                    "measured": result.measured,
                    "problems": result.problems,
                }
            )
            # Only the primary is a pass bar. The second candidate is expected
            # to fail the scene check, and reporting that is the point of
            # keeping it registered.
            if pin is datasets.PRIMARY and not result.ok:
                failed = True
        return 1 if failed else 0

    if cmd == "controllers":
        from vla_pick_and_place.env import contract
        from vla_pick_and_place.policy import controllers

        measured = contract.capture()
        for c in controllers.REGISTRY.values():
            _print(
                {
                    "key": c.key,
                    "label": c.label,
                    "available": c.available,
                    "reason": c.unavailable_reason,
                    "repo_id": c.repo_id,
                    "family": c.family,
                    "required_device": c.required_device,
                    "env_id": c.env_id,
                    "published_eval": c.published_eval,
                    "local_eval": c.local_eval,
                    "schema_mismatches": controllers.check_against_env(c, measured),
                }
            )
        print(
            f"available controllers: {[c.key for c in controllers.available()]}",
            file=sys.stderr,
        )
        return 0

    if cmd == "expert":
        from vla_pick_and_place.data.expert import evaluate

        n = int(rest[0]) if rest else 30
        start = int(rest[1]) if len(rest) > 1 else 0
        result = evaluate(n_seeds=n, start=start)
        _print(result)
        return 0

    if cmd == "record":
        from vla_pick_and_place.data.record import record

        n = int(rest[0]) if rest else 50
        summary = record(n_episodes=n)
        _print(summary)
        print(
            f"\nwrote {summary['episodes']} episodes to {summary['root']}\n"
            "NOT pushed to the Hub. Review it first.",
            file=sys.stderr,
        )
        return 0 if summary["episodes"] == n else 1

    if cmd == "sim":
        from vla_pick_and_place.config import VIZ_DIR
        from vla_pick_and_place.demo.session import SimWorker
        from vla_pick_and_place.viz.rerun_logger import RerunLogger

        seed = int(rest[0]) if rest else 0
        steps = int(rest[1]) if len(rest) > 1 else 60
        worker = SimWorker().start()
        logger = RerunLogger(save_path=VIZ_DIR / f"sim_seed{seed}.rrd")
        try:
            frame = worker.reset(seed=seed)
            logger.log(frame)
            last = frame
            for frame in worker.hold(n_steps=steps):
                logger.log(frame)
                last = frame
            print(
                f"seed {seed}: {last.step} steps, reward {last.reward}, "
                f"success={last.success}, target={last.info.get('target_object')}"
            )
            print(f"open with: rerun {logger.save_path}")
        finally:
            logger.close()
            worker.close()
        return 0

    if cmd == "play":
        from vla_pick_and_place.config import VIZ_DIR
        from vla_pick_and_place.data import datasets
        from vla_pick_and_place.demo.session import dataset_frames
        from vla_pick_and_place.viz.rerun_logger import RerunLogger

        episode = int(rest[0]) if rest else 0
        player = datasets.EpisodePlayer(datasets.PRIMARY, episode=episode)
        logger = RerunLogger(save_path=VIZ_DIR / f"episode_{episode}.rrd")
        try:
            n = 0
            for frame in dataset_frames(player):
                logger.log(frame)
                n += 1
            print(f"{datasets.PRIMARY.repo_id} episode {episode}: {n} recorded frames")
            print(f"open with: rerun {logger.save_path}")
        finally:
            logger.close()
        return 0

    print(f"unknown subcommand: {cmd}", file=sys.stderr)
    print(__doc__.strip(), file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
