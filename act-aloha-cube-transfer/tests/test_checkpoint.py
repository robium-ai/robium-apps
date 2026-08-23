import json

import pytest

from act_aloha_cube_transfer import config
from act_aloha_cube_transfer.checkpoint import MIGRATED_FILES, SOURCE_FILES, ensure_official_checkpoint


@pytest.mark.slow
def test_official_checkpoint_migration_is_auditable():
    checkpoint = ensure_official_checkpoint()
    manifest = json.loads((checkpoint / "manifest.json").read_text())
    assert manifest["status"] == "ready"
    assert manifest["repo_id"] == config.MODEL_REPO_ID
    assert manifest["revision"] == config.MODEL_REVISION
    assert manifest["migration"]["implementation"] == "lerobot.processor.migrate_policy_normalization"
    assert manifest["migration"]["source_modified"] is False
    assert set(manifest["source_files"]) == set(SOURCE_FILES)
    assert set(manifest["migrated_files"]) == set(MIGRATED_FILES)
    assert manifest["contract"]["chunk_size"] == config.ACTION_CHUNK_SIZE
