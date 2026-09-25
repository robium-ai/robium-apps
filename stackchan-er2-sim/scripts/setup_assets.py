#!/usr/bin/env python3
"""Fetch pinned, cacheable third-party runtime assets."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local"
MODELS = LOCAL / "models"
SIM = LOCAL / "stackchan-simulator"
SIM_REPOSITORY = "https://github.com/qua121/stackchan-simulator.git"
SIM_REVISION = "f6a3d57ffe6888e64c873b3b18a945ca06673ff3"

ASSETS = {
    "ggml-base.en-q5_1.bin": (
        "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en-q5_1.bin",
        "4baf70dd0d7c4247ba2b81fafd9c01005ac77c2f9ef064e00dcf195d0e2fdd2f",
    ),
    "kokoro-v1.0.int8.onnx": (
        (
            "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
            "model-files-v1.0/kokoro-v1.0.int8.onnx"
        ),
        "6e742170d309016e5891a994e1ce1559c702a2ccd0075e67ef7157974f6406cb",
    ),
    "voices-v1.0.bin": (
        (
            "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
            "model-files-v1.0/voices-v1.0.bin"
        ),
        "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d",
    ),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(url: str, target: Path, expected: str) -> None:
    if target.is_file() and sha256(target) == expected:
        print(f"PASS cached {target.name}")
        return
    part = target.with_suffix(target.suffix + ".part")
    part.unlink(missing_ok=True)
    print(f"FETCH {target.name}", flush=True)
    with urllib.request.urlopen(url) as response, part.open("wb") as output:
        shutil.copyfileobj(response, output)
    actual = sha256(part)
    if actual != expected:
        part.unlink(missing_ok=True)
        raise RuntimeError(f"checksum mismatch for {target.name}: {actual}")
    part.replace(target)
    print(f"PASS verified {target.name}")


def setup_simulator() -> None:
    if not (SIM / ".git").is_dir():
        if SIM.exists():
            raise RuntimeError(f"{SIM} exists but is not a git checkout")
        subprocess.run(
            ["git", "clone", "--no-checkout", "--filter=blob:none", SIM_REPOSITORY, str(SIM)],
            check=True,
        )
    subprocess.run(
        ["git", "-C", str(SIM), "fetch", "--depth", "1", "origin", SIM_REVISION],
        check=True,
    )
    subprocess.run(["git", "-C", str(SIM), "checkout", "--detach", SIM_REVISION], check=True)
    actual = subprocess.run(
        ["git", "-C", str(SIM), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if actual != SIM_REVISION:
        raise RuntimeError(f"simulator revision mismatch: {actual}")
    print(f"PASS stackchan-simulator {actual[:12]}")


def main() -> None:
    LOCAL.mkdir(exist_ok=True)
    MODELS.mkdir(exist_ok=True)
    setup_simulator()
    for name, (url, checksum) in ASSETS.items():
        fetch(url, MODELS / name, checksum)
    print("ASSETS READY")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"ERROR {error}", file=sys.stderr)
        raise SystemExit(1) from error
