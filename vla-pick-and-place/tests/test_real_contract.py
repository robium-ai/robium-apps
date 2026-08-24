from pathlib import Path
from types import SimpleNamespace

import pytest

from vla_pick_and_place.config import (
    CHECKPOINT_REVISION,
    TOKENIZER_FILES,
)
from vla_pick_and_place.real import (
    validate_checkpoint_snapshot,
    validate_tied_embedding,
)


class Parameter:
    def __init__(self, pointer: int) -> None:
        self.pointer = pointer

    def data_ptr(self) -> int:
        return self.pointer


def _policy(embedding: Parameter, head: Parameter):
    language_model = SimpleNamespace(embed_tokens=SimpleNamespace(weight=embedding))
    paligemma = SimpleNamespace(
        model=SimpleNamespace(language_model=language_model),
        lm_head=SimpleNamespace(weight=head),
    )
    return SimpleNamespace(
        model=SimpleNamespace(
            paligemma_with_expert=SimpleNamespace(paligemma=paligemma)
        )
    )


def test_tied_embedding_validation_accepts_shared_storage() -> None:
    validate_tied_embedding(_policy(Parameter(42), Parameter(42)))


def test_tied_embedding_validation_fails_closed() -> None:
    with pytest.raises(RuntimeError, match="embedding and language head are not tied"):
        validate_tied_embedding(_policy(Parameter(1), Parameter(2)))


def test_snapshot_requires_exact_tokenizer_revision(tmp_path: Path) -> None:
    (tmp_path / "REVISION").write_text(f"{CHECKPOINT_REVISION}\n")
    for name in TOKENIZER_FILES:
        target = tmp_path / "tokenizer" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"x")
    (tmp_path / "tokenizer" / "REVISION").write_text("wrong\n")

    with pytest.raises(RuntimeError, match="tokenizer REVISION"):
        validate_checkpoint_snapshot(tmp_path)
