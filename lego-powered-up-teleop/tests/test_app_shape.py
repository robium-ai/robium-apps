from __future__ import annotations

from pathlib import Path

from lego_powered_up_teleop.run import APP_ROOT, HUB_PROGRAM, build_parser


def test_required_app_files_exist() -> None:
    for relative in ("README.md", "robium-app.yaml", "docs/architecture-brief.md", "app"):
        assert (APP_ROOT / relative).is_file()


def test_hub_program_is_valid_python_syntax() -> None:
    source = HUB_PROGRAM.read_text()
    compile(source, str(HUB_PROGRAM), "exec")


def test_hub_program_contains_independent_watchdog_and_final_brake() -> None:
    source = HUB_PROGRAM.read_text()
    assert "WATCHDOG_MS = 400" in source
    assert "watchdog.time() >= WATCHDOG_MS" in source
    assert "finally:\n    brake()" in source


def test_hub_program_accepts_encoded_and_simple_motors() -> None:
    source = HUB_PROGRAM.read_text()
    assert "return Motor(port, positive_direction)" in source
    assert "return DCMotor(port, positive_direction)" in source


def test_cli_commands_parse() -> None:
    parser = build_parser()
    for command in ("hubs", "doctor", "gamepad", "run", "smoke"):
        assert parser.parse_args([command]).command == command


def test_app_launcher_is_executable() -> None:
    assert Path(APP_ROOT / "app").stat().st_mode & 0o111
