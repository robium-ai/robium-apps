"""Durable, sanitized startup diagnostics for remote GPU runs."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SECRET_NAME = re.compile(r"(?:TOKEN|SECRET|KEY|PASSWORD|CREDENTIAL)", re.IGNORECASE)
_HF_TOKEN = re.compile(r"\bhf_[A-Za-z0-9_-]{16,}\b")
_BEARER = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{12,}")
_MAX_MESSAGE_LENGTH = 2_000


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def _sanitize(message: str, environment: Mapping[str, str]) -> str:
    sanitized = message
    secrets = {
        value
        for name, value in environment.items()
        if _SECRET_NAME.search(name) and len(value) >= 8
    }
    for secret in sorted(secrets, key=len, reverse=True):
        sanitized = sanitized.replace(secret, "[REDACTED]")
    sanitized = _HF_TOKEN.sub("[REDACTED]", sanitized)
    sanitized = _BEARER.sub(r"\1[REDACTED]", sanitized)
    return sanitized[:_MAX_MESSAGE_LENGTH]


def write_phase(output: Path, stage: str, *, status: str = "running") -> None:
    """Atomically replace the current startup phase marker."""
    _write_atomic(
        output / "phase.json",
        {
            "schema_version": "1.0.0",
            "stage": stage,
            "status": status,
            "timestamp": _timestamp(),
        },
    )


def read_phase(output: Path) -> str:
    """Return the last durable stage, or ``unknown`` if no valid marker exists."""
    try:
        marker = json.loads((output / "phase.json").read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return "unknown"
    stage = marker.get("stage")
    return stage if isinstance(stage, str) and stage else "unknown"


def write_failure(
    output: Path,
    error: BaseException,
    *,
    environment: Mapping[str, str],
    return_code: int | None = None,
) -> None:
    """Persist a bounded error summary without credentials or a traceback."""
    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "stage": read_phase(output),
        "exception_type": type(error).__name__,
        "message": _sanitize(str(error), environment),
        "timestamp": _timestamp(),
    }
    if return_code is not None:
        payload["return_code"] = return_code
    _write_atomic(output / "failure.json", payload)
