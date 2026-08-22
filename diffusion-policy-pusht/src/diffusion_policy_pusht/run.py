"""Config-driven entry point for training, calibration, and evaluation stages."""

from __future__ import annotations

import shutil
import subprocess
import sys

from diffusion_policy_pusht import config


def _run(cmd: list[str]) -> int:
    print(f"$ {' '.join(map(str, cmd))}", flush=True)
    return subprocess.run(cmd).returncode


def _train_to_5k() -> int:
    if config.TRAIN_OUTPUT_DIR.exists():
        print(
            f"refusing to overwrite {config.TRAIN_OUTPUT_DIR}; "
            "resume it or move it aside explicitly",
            file=sys.stderr,
        )
        return 2
    return _run(config.train_initial_ladder_cmd())


def _resume_to(target: int) -> int:
    if target not in config.CHECKPOINT_STEPS:
        print(f"target must be one of {config.CHECKPOINT_STEPS}, got {target}", file=sys.stderr)
        return 2
    available = config.available_checkpoint_steps()
    if not available:
        print("no ladder run exists; run train-to-5k first", file=sys.stderr)
        return 2
    latest = max(available)
    if target <= latest:
        print(f"checkpoint {target} already exists (latest={latest})", file=sys.stderr)
        return 2
    if target > config.CALIBRATION_STEP and not config.CALIBRATION_RESULTS.is_file():
        print(
            f"refusing to resume past {config.CALIBRATION_STEP}: "
            "run `make calibrate` and inspect its fixed-seed result first",
            file=sys.stderr,
        )
        return 2
    return _run(config.resume_ladder_cmd(target))


def main() -> int:
    stage = sys.argv[1] if len(sys.argv) > 1 else ""
    if stage == "train-smoke":
        shutil.rmtree(config.SMOKE_TRAIN_OUTPUT_DIR, ignore_errors=True)
        return _run(config.train_smoke_cmd())
    if stage == "eval-trained":
        shutil.rmtree(config.SMOKE_EVAL_OUTPUT_DIR, ignore_errors=True)
        return _run(
            config.eval_cmd(
                config.latest_checkpoint(config.SMOKE_TRAIN_OUTPUT_DIR),
                config.SMOKE_EVAL_EPISODES,
                config.SMOKE_EVAL_BATCH_SIZE,
                config.SMOKE_EVAL_OUTPUT_DIR,
            )
        )
    if stage == "train-to-5k":
        return _train_to_5k()
    if stage == "resume-to":
        if len(sys.argv) != 3:
            print("usage: python -m diffusion_policy_pusht.run resume-to <steps>", file=sys.stderr)
            return 2
        return _resume_to(int(sys.argv[2]))
    if stage == "train-ladder":
        if not config.TRAIN_OUTPUT_DIR.exists():
            rc = _train_to_5k()
            if rc:
                return rc
        for target in config.CHECKPOINT_STEPS:
            available = config.available_checkpoint_steps()
            if target in available:
                continue
            rc = _resume_to(target)
            if rc:
                return rc
        return 0
    if stage == "calibrate":
        from diffusion_policy_pusht.ladder import calibrate

        return calibrate()
    if stage == "eval-ladder":
        from diffusion_policy_pusht.ladder import eval_ladder

        return eval_ladder()
    if stage == "prepare-official":
        from diffusion_policy_pusht.official import main as prepare_official

        return prepare_official()
    print(
        "usage: python -m diffusion_policy_pusht.run "
        "<prepare-official|train-smoke|eval-trained|train-to-5k|resume-to STEPS|"
        "train-ladder|calibrate|eval-ladder>"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
