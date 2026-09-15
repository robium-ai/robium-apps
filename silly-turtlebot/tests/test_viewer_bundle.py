from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path


def test_bundle_revisions_extension_and_migrates_layout_once(tmp_path: Path) -> None:
    index = tmp_path / "index.html"
    extension = tmp_path / "dashboard.foxe"
    layout = tmp_path / "layout.json"
    index.write_text(
        '<html><head><script defer src="main.js"></script></head></html>',
        encoding="utf-8",
    )
    extension.write_bytes(b"extension contents")
    layout.write_text('{"layout":"current"}', encoding="utf-8")

    subprocess.run(
        [
            sys.executable,
            str(
                Path(__file__).parents[1]
                / "simulation"
                / "bundle_extension.py"
            ),
            str(index),
            str(extension),
            str(layout),
        ],
        check=True,
    )

    output = index.read_text(encoding="utf-8")
    extension_revision = hashlib.sha256(extension.read_bytes()).hexdigest()[:16]
    layout_revision = "v2-" + hashlib.sha256(layout.read_bytes()).hexdigest()[:16]
    assert f"preinstall-extension.mjs?v={extension_revision}" in output
    assert f'main.js?v={extension_revision}' in output
    assert f'!== "{layout_revision}"' in output
    assert 'indexedDB.open("lichtblick-layouts", 1)' in output
    assert 'const profileDataKey = "studio.profile-data"' in output
    assert "profile.currentLayoutId = canonicalLayoutId" in output
    assert "robium.silly-turtlebot.layout-revision-v2" in output
