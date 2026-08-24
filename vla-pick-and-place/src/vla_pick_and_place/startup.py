"""Baked checkpoint bootstrap and offline gateway startup."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from vla_pick_and_place.bootstrap import bootstrap_checkpoint, offline_environment
from vla_pick_and_place.real import validate_checkpoint_snapshot

Execute = Callable[[str, Sequence[str], Mapping[str, str]], object]
Run = Callable[..., object]


def cuda_preflight(output: Path | None) -> dict[str, Any]:
    """Verify and record CUDA compatibility before any checkpoint download."""
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA preflight failed: torch.cuda.is_available() is false")
    torch.cuda.reset_peak_memory_stats()
    device = torch.device("cuda:0")
    properties = torch.cuda.get_device_properties(device)
    tensor_result = (torch.tensor([1.0, 2.0], device=device) * 2).sum().item()
    if tensor_result != 6.0:
        raise RuntimeError(f"CUDA preflight tensor result was {tensor_result}, expected 6")
    nvidia_smi = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=name,driver_version,memory.total",
            "--format=csv,noheader,nounits",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    report = {
        "compute_capability": list(torch.cuda.get_device_capability(device)),
        "device_name": torch.cuda.get_device_name(device),
        "device_total_memory_bytes": properties.total_memory,
        "minimal_tensor_result": tensor_result,
        "nvidia_smi": nvidia_smi,
        "peak_memory_bytes": torch.cuda.max_memory_allocated(device),
        "supported_architectures": torch.cuda.get_arch_list(),
        "torch_cuda_version": torch.version.cuda,
        "torch_version": torch.__version__,
    }
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"CUDA PREFLIGHT {json.dumps(report, sort_keys=True)}", flush=True)
    return report


def _prepare_checkpoint(
    checkpoint_path: Path,
    *,
    environment: Mapping[str, str],
    preflight_output: Path | None,
) -> None:
    cuda_preflight(preflight_output)
    try:
        validate_checkpoint_snapshot(checkpoint_path)
    except RuntimeError:
        bootstrap_checkpoint(checkpoint_path, token=environment.get("HF_TOKEN", ""))


def launch_gateway(
    *,
    checkpoint_path: Path,
    environment: Mapping[str, str],
    execute: Execute = os.execvpe,
) -> None:
    """Prepare the exact checkpoint when needed, then exec the gateway offline."""
    _prepare_checkpoint(
        checkpoint_path, environment=environment, preflight_output=None
    )

    command = [sys.executable, "-m", "vla_pick_and_place.gateway"]
    print("CHECKPOINT READY; STARTING OFFLINE GATEWAY", flush=True)
    execute(command[0], command, offline_environment(environment))


def launch_feasibility(
    *,
    checkpoint_path: Path,
    output: Path,
    environment: Mapping[str, str],
    run: Run = subprocess.run,
    execute: Execute = os.execvpe,
) -> None:
    """Run one measured rollout, persist evidence, then serve the gateway."""
    _prepare_checkpoint(
        checkpoint_path,
        environment=environment,
        preflight_output=output / "cuda-preflight.json",
    )
    command = [
        sys.executable,
        "-m",
        "vla_pick_and_place.cli",
        "feasibility",
        "--output",
        str(output),
    ]
    offline = offline_environment(environment)
    run(command, check=True, env=offline)
    print("FEASIBILITY COMPLETE; STARTING OFFLINE GATEWAY", flush=True)
    gateway = [sys.executable, "-m", "vla_pick_and_place.gateway"]
    execute(gateway[0], gateway, offline)


def main() -> None:
    checkpoint_path = Path(
        os.environ.get("VLA_CHECKPOINT_PATH", "/models/pi05-libero-v044")
    )
    mode = os.environ.get("VLA_STARTUP_MODE", "gateway")
    if mode == "gateway":
        launch_gateway(checkpoint_path=checkpoint_path, environment=os.environ)
        return
    if mode == "feasibility":
        output = Path(
            os.environ.get(
                "VLA_EVIDENCE_OUTPUT", "/models/issue-69-feasibility-retry"
            )
        )
        launch_feasibility(
            checkpoint_path=checkpoint_path,
            output=output,
            environment=os.environ,
        )
        return
    raise RuntimeError("VLA_STARTUP_MODE must be gateway or feasibility")


if __name__ == "__main__":
    main()
