from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_required_app_files_exist() -> None:
    for path in (
        ROOT / "README.md",
        ROOT / "robium-app.yaml",
        ROOT / "assets" / "stills" / "stackchan-er2-sim-macos.png",
        ROOT / "docs" / "architecture-brief.md",
        ROOT / "scripts" / "setup_assets.py",
        ROOT / "src" / "stackchan_er2_sim" / "static" / "index.html",
    ):
        assert path.is_file()


def test_app_entrypoint_is_executable() -> None:
    assert (ROOT / "app").stat().st_mode & 0o111


def test_onboarding_view_is_robot_only() -> None:
    html = (ROOT / "src" / "stackchan_er2_sim" / "static" / "index.html").read_text()
    css = (ROOT / "src" / "stackchan_er2_sim" / "static" / "style.css").read_text()

    assert "advanced robot controls" not in html.lower()
    assert "overflow: hidden" in css
