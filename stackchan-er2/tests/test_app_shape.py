from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_required_reference_app_files_exist() -> None:
    for path in (
        ROOT / "README.md",
        ROOT / "robium-app.yaml",
        ROOT / "docs" / "architecture-brief.md",
        ROOT / "firmware" / "stackchan_er2" / "stackchan_er2.ino",
        ROOT / "lego_hub" / "main.py",
    ):
        assert path.is_file()


def test_app_entrypoint_is_executable() -> None:
    assert (ROOT / "app").stat().st_mode & 0o111
