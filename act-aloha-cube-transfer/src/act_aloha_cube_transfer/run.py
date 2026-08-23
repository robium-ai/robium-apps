from __future__ import annotations

import argparse

from act_aloha_cube_transfer.calibration import run_calibration
from act_aloha_cube_transfer.checkpoint import ensure_official_checkpoint


def main() -> int:
    parser = argparse.ArgumentParser(description="ACT ALOHA operator commands")
    parser.add_argument("command", choices=("prepare-official", "calibrate"))
    args = parser.parse_args()
    if args.command == "prepare-official":
        path = ensure_official_checkpoint()
        print(f"official ACT checkpoint ready: {path}")
    elif args.command == "calibrate":
        path = run_calibration()
        print(f"calibration evidence ready: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
