"""Repository-local command line surface."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import threading
import webbrowser

import uvicorn

from .config import KOKORO_MODEL, KOKORO_VOICES, SIM_REVISION, SIM_SOURCE, WHISPER_MODEL
from .router import route


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Local-first Stack-chan MuJoCo demo")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor")
    commands.add_parser("demo")
    run = commands.add_parser("run")
    run.add_argument("--brain", choices=("local", "er2"), default="local")
    run.add_argument("--host", default="127.0.0.1")
    run.add_argument("--port", type=int, default=8017)
    run.add_argument("--no-open", action="store_true")
    return root


def doctor() -> int:
    checks: list[tuple[str, bool, str]] = []
    checks.append(("git", shutil.which("git") is not None, shutil.which("git") or "missing"))
    revision = "missing"
    if (SIM_SOURCE / ".git").is_dir():
        revision = subprocess.run(
            ["git", "-C", str(SIM_SOURCE), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
        ).stdout.strip()
    checks.append(("simulator", revision == SIM_REVISION, revision or "missing"))
    checks.extend(
        [
            ("whisper", WHISPER_MODEL.is_file(), str(WHISPER_MODEL)),
            ("kokoro-model", KOKORO_MODEL.is_file(), str(KOKORO_MODEL)),
            ("kokoro-voices", KOKORO_VOICES.is_file(), str(KOKORO_VOICES)),
        ]
    )
    checks.append(
        (
            "er2-key",
            bool(os.environ.get("GEMINI_API_KEY")),
            "set (optional)" if os.environ.get("GEMINI_API_KEY") else "unset (optional)",
        )
    )
    failed = False
    for name, passed, detail in checks:
        optional = name == "er2-key"
        print(f"{'PASS' if passed else ('WARN' if optional else 'FAIL')} {name}: {detail}")
        failed = failed or (not passed and not optional)
    return int(failed)


def demo() -> int:
    cases = ("look left", "nod yes", "track me", "stop tracking", "introduce yourself")
    for text in cases:
        command = route(text)
        print(f"{text!r} -> {command.action}; tracking={command.tracking}; {command.speech}")
    print("STACKCHAN SIM POC PASS")
    return 0


def run(host: str, port: int, brain: str, no_open: bool) -> int:
    if brain == "er2" and not os.environ.get("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY is required for --brain er2")
    from .server import create_app

    url = f"http://{host}:{port}"
    print(f"Stack-chan ready at {url} (brain={brain})")
    if not no_open:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run(create_app(brain_mode=brain), host=host, port=port, log_level="info")
    return 0


def main() -> None:
    arguments = parser().parse_args()
    try:
        if arguments.command == "doctor":
            code = doctor()
        elif arguments.command == "demo":
            code = demo()
        else:
            code = run(arguments.host, arguments.port, arguments.brain, arguments.no_open)
    except (RuntimeError, ValueError) as error:
        print(f"ERROR {error}")
        code = 1
    raise SystemExit(code)
