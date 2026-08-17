"""A missing/incomplete checkpoint must fail with a message that names its fix.

Two real failure modes this app has actually hit, both of which used to
surface as an obscure traceback several frames inside `from_pretrained`:

  1. Wrong namespace. `DEMO_CHECKPOINT` pointed at `robium/train_...` for
     two weeks; HF Jobs pushes to the submitting *user's* namespace, so the
     artifact was under `robium-admin/`. Every "trained" run 404'd.
  2. Weights-less repo. `robium-admin/train_2026-08-04_05-35-54` exists and
     resolves fine — it just has no `model.safetensors`, because the job
     died before pushing. Repo-exists is NOT enough; the weights decide.
"""

import pytest

from vla_pick_and_place.policy.resolve import (
    CheckpointError,
    resolve_checkpoint,
)


def test_local_path_resolves(tmp_path):
    ckpt = tmp_path / "pretrained_model"
    ckpt.mkdir()
    (ckpt / "model.safetensors").write_bytes(b"")
    assert resolve_checkpoint(str(ckpt)) == str(ckpt)


def test_local_path_without_weights_is_rejected(tmp_path):
    ckpt = tmp_path / "pretrained_model"
    ckpt.mkdir()
    (ckpt / "train_config.json").write_text("{}")
    with pytest.raises(CheckpointError, match="no model weights"):
        resolve_checkpoint(str(ckpt))


def test_missing_hub_repo_names_the_namespace_trap():
    """The error must mention the namespace, because that was the bug."""
    with pytest.raises(CheckpointError, match="namespace"):
        resolve_checkpoint(
            "robium/train_2026-07-15_08-09-36",
            _lister=_raise_missing,
        )


def test_hub_repo_without_weights_is_rejected():
    with pytest.raises(CheckpointError, match="no model weights"):
        resolve_checkpoint(
            "robium-admin/train_2026-08-04_05-35-54",
            _lister=lambda repo_id: ["train_config.json", ".gitattributes"],
        )


def test_hub_repo_with_weights_resolves():
    repo = "robium-admin/train_2026-07-15_08-09-36"
    assert (
        resolve_checkpoint(
            repo,
            _lister=lambda repo_id: ["config.json", "model.safetensors"],
        )
        == repo
    )


def _raise_missing(repo_id):
    raise FileNotFoundError(repo_id)
