"""First-user credential gates, isolated from Docker and secret stores."""

import os
from pathlib import Path
import subprocess

import pytest


APP = Path(__file__).resolve().parents[1] / "app"


@pytest.fixture
def cli_env(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls"
    for command in ("docker", "doppler", "uv"):
        executable = bin_dir / command
        executable.write_text(
            '#!/bin/sh\n'
            f'printf "%s\\n" "{command} $*" >> "$TEST_CALLS"\n'
            'case "$*" in *"real/compose.yaml ps"*) printf "%s" "${TEST_REAL_SERVICE:-}" ;; esac\n'
            'exit 0\n'
        )
        executable.chmod(0o755)
    env = {
        key: value for key, value in os.environ.items()
        if not key.startswith(("GEMINI_", "GOOGLE_", "DOPPLER_", "SILLY_"))
    }
    env.update(PATH=f"{bin_dir}:/usr/bin:/bin", TEST_CALLS=str(calls))
    return env, calls


@pytest.mark.parametrize("arguments", [
    ["run"], ["sim-up"], ["live", "--text", "Look around"],
    ["sim-live", "--text", "Look around"],
    ["run", "--real", "--robot-url", "http://example.invalid:8088"],
])
def test_missing_key_fails_before_build_or_service_changes(cli_env, arguments):
    env, calls = cli_env
    result = subprocess.run(["/bin/bash", str(APP), *arguments], env=env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert "GEMINI_API_KEY is unset" in result.stderr
    assert not calls.exists(), "No Docker, uv, or secret-store calls before credentials"


def test_exported_key_uses_fast_simulation_without_doppler(cli_env):
    env, calls = cli_env
    env["GEMINI_API_KEY"] = "test-only-not-a-real-key"
    result = subprocess.run(["/bin/bash", str(APP), "run"], env=env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0
    assert "TurtleBot 3 Waffle Pi" in result.stdout
    recorded = calls.read_text()
    assert "up -d --no-build sim agent" in recorded
    assert "doppler" not in recorded
    assert " down " not in recorded
    assert env["GEMINI_API_KEY"] not in result.stdout + result.stderr + recorded


def test_doppler_requires_explicit_project_and_config(cli_env):
    env, calls = cli_env
    env["DOPPLER_PROJECT"] = "test-project"
    result = subprocess.run(["/bin/bash", str(APP), "run"], env=env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert not calls.exists()
    env["DOPPLER_CONFIG"] = "test-config"
    result = subprocess.run(["/bin/bash", str(APP), "run"], env=env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0
    assert "doppler run --project test-project --config test-config --" in calls.read_text()


def test_existing_real_session_is_not_stopped(cli_env):
    env, calls = cli_env
    env.update(GEMINI_API_KEY="test-only-not-a-real-key", TEST_REAL_SERVICE="existing-container")
    result = subprocess.run(["/bin/bash", str(APP), "run"], env=env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert "will not stop them automatically" in result.stderr
    recorded = calls.read_text()
    assert " down " not in recorded
    assert " build " not in recorded
    assert " up " not in recorded
