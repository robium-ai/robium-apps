import json
from pathlib import Path

from PIL import Image

from act_aloha_cube_transfer import config
from act_aloha_cube_transfer.calibration import published_evidence


def test_published_evidence_stays_separate_and_attributed():
    evidence = published_evidence()
    source = json.loads((config.MODEL_SOURCE_DIR / "eval_info.json").read_text())
    assert evidence["kind"] == "published"
    assert evidence["episodes"] == 500
    assert evidence["success_rate"] == float(source["aggregated"]["pc_success"]) / 100.0
    assert config.MODEL_REPO_ID in evidence["source"]


def test_article_media_records_a_real_successful_transfer():
    gif = Path("assets/gifs/transfer-seed-1001.gif")
    metadata = json.loads(gif.with_suffix(".json").read_text())
    assert metadata["checkpoint"]["revision"] == config.MODEL_REVISION
    assert metadata["seed"] == 1001
    assert metadata["execution_horizon"] == 100
    assert metadata["success"] is True
    assert metadata["terminal_phase"] == "transfer complete"
    assert 12 <= metadata["duration_seconds"] <= 18
    assert metadata["gif_bytes"] == gif.stat().st_size < 8 * 1024 * 1024
    with Image.open(gif) as image:
        assert image.size == (640, 480)
        assert image.n_frames == metadata["frames"]
