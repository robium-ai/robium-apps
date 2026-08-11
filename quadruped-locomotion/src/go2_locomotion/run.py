"""Thin CLI that runs Isaac Lab from the single-source commands in config.py.

RUNS ON THE POD ONLY (it subprocess-invokes Isaac Lab, which has no macOS path).
Launched with ISAACLAB_ROOT as the working directory so Isaac Lab's logs/ land
under the IsaacLab tree.

    python -m go2_locomotion.run list-envs
    python -m go2_locomotion.run train          # SMOKE profile (pass-bar)
    python -m go2_locomotion.run train --full    # FULL walking-policy run
    python -m go2_locomotion.run train --full --video
    python -m go2_locomotion.run play --video    # roll out latest checkpoint

Every invocation is built by config.py, never hand-typed here, so the smoke run
and a hand-run stage cannot drift.
"""

import subprocess
import sys

from . import config


def _run(cmd: list[str]) -> int:
    print("+ (cwd=%s) %s" % (config.ISAACLAB_ROOT, " ".join(cmd)), flush=True)
    # cwd=ISAACLAB_ROOT: Isaac Lab resolves its script paths and writes logs/
    # relative to the IsaacLab checkout.
    return subprocess.call(cmd, cwd=str(config.ISAACLAB_ROOT))


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(__doc__)
        return 2
    sub, rest = argv[0], argv[1:]
    full = "--full" in rest
    video = "--video" in rest

    if sub == "list-envs":
        return _run(config.list_envs_cmd())
    if sub == "train":
        return _run(config.train_cmd(full=full, video=video))
    if sub == "play":
        return _run(config.play_cmd(video=video))
    print(f"unknown subcommand: {sub}\n{__doc__}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
