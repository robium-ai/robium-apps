from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from vla_pick_and_place.config import (
    CHECKPOINT_REVISION,
    TOKENIZER_FILES,
)
from vla_pick_and_place.real import (
    _batch_libero_robot_state,
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


def test_libero_robot_state_is_batched_without_mutating_images_or_input() -> None:
    image = np.zeros((256, 256, 3), dtype=np.uint8)
    quaternion = np.array([0.0, 0.0, 0.0, 1.0])
    observation = {
        "pixels": {"image": image},
        "robot_state": {
            "eef": {
                "pos": np.zeros(3),
                "quat": quaternion,
                "mat": np.eye(3),
            },
            "gripper": {"qpos": np.zeros(2), "qvel": np.zeros(2)},
            "joints": {"pos": np.zeros(7), "vel": np.zeros(7)},
        },
    }

    batched = _batch_libero_robot_state(observation)

    assert batched["pixels"]["image"] is image
    assert batched["robot_state"]["eef"]["pos"].shape == (1, 3)
    assert batched["robot_state"]["eef"]["quat"].shape == (1, 4)
    assert batched["robot_state"]["eef"]["mat"].shape == (1, 3, 3)
    assert batched["robot_state"]["gripper"]["qpos"].shape == (1, 2)
    assert batched["robot_state"]["joints"]["pos"].shape == (1, 7)
    assert observation["robot_state"]["eef"]["quat"] is quaternion
    assert observation["robot_state"]["eef"]["quat"].shape == (4,)
