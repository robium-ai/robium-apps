import json

from act_aloha_cube_transfer import config
from act_aloha_cube_transfer.calibration import published_evidence


def test_published_evidence_stays_separate_and_attributed():
    evidence = published_evidence()
    source = json.loads((config.MODEL_SOURCE_DIR / "eval_info.json").read_text())
    assert evidence["kind"] == "published"
    assert evidence["episodes"] == 500
    assert evidence["success_rate"] == float(source["aggregated"]["pc_success"]) / 100.0
    assert config.MODEL_REPO_ID in evidence["source"]
