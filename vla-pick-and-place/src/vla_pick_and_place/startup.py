"""Baked checkpoint bootstrap and offline gateway startup."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from vla_pick_and_place.bootstrap import bootstrap_checkpoint, offline_environment
from vla_pick_and_place.real import validate_checkpoint_snapshot

Execute = Callable[[str, Sequence[str], Mapping[str, str]], object]


def launch_gateway(
    *,
    checkpoint_path: Path,
    environment: Mapping[str, str],
    execute: Execute = os.execvpe,
) -> None:
    """Prepare the exact checkpoint when needed, then exec the gateway offline."""
    try:
        validate_checkpoint_snapshot(checkpoint_path)
    except RuntimeError:
        bootstrap_checkpoint(checkpoint_path, token=environment.get("HF_TOKEN", ""))

    command = [sys.executable, "-m", "vla_pick_and_place.gateway"]
    print("CHECKPOINT READY; STARTING OFFLINE GATEWAY", flush=True)
    execute(command[0], command, offline_environment(environment))


def main() -> None:
    checkpoint_path = Path(
        os.environ.get("VLA_CHECKPOINT_PATH", "/models/pi05-libero-v044")
    )
    launch_gateway(checkpoint_path=checkpoint_path, environment=os.environ)


if __name__ == "__main__":
    main()
