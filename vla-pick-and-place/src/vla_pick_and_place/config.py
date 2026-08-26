"""Immutable benchmark configuration and visitor prompt handling."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape

CHECKPOINT_ID = "lerobot/pi05_libero_finetuned_v044"
CHECKPOINT_REVISION = "8e174154ef5f6c60a8da12ae99c303d8963138c1"
CHECKPOINT_MODEL_BYTES = 7_473_096_344
CHECKPOINT_MODEL_SHA256 = (
    "877b3ec1130548b69af7f8aeef3ec9d3fc7738040f0b9beb490857ec970997ae"
)
TOKENIZER_ID = "google/paligemma-3b-pt-224"
TOKENIZER_REVISION = "35e4f46485b4d07967e7e9935bc3786aad50687c"
TOKENIZER_FILES = (
    "added_tokens.json",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer.model",
    "tokenizer_config.json",
)
LEROBOT_REVISION = "8fff0fde7c79f23a93d845d1a50e985de01f8b8a"
LIBERO_REVISION = "8f1084e3132a39270c3a13ebe37270a43ece2a01"
EVIDENCE_REPO_ID = "robium/pi05-libero-goal-task-8-evidence"

TASK_SUITE = "libero_goal"
TASK_ID = 8
TASK_NAME = "put_the_bowl_on_the_plate"
CANONICAL_PROMPT = "put the bowl on the plate"
MAX_PROMPT_CODEPOINTS = 200
MAX_STEPS = 300
N_ACTION_STEPS = 10
BATCH_SIZE = 1


@dataclass(frozen=True)
class CuratedState:
    state_id: int
    label: str


@dataclass(frozen=True)
class EpisodeSpec:
    episode_index: int
    state_id: int
    seed: int


@dataclass(frozen=True)
class Prompt:
    text: str
    provenance: str


CURATED_STATES = tuple(
    CuratedState(state_id=index, label=f"Official fixed state {index}")
    for index in range(3)
)
PUBLICATION_EPISODES = tuple(
    EpisodeSpec(episode_index=index, state_id=index, seed=1000 + index)
    for index in range(20)
)


def classify_prompt(value: str) -> Prompt:
    """Normalize a prompt and label only the exact benchmark prompt as supported."""
    text = value.strip()
    if not text:
        raise ValueError("prompt must be nonempty")
    if len(text) > MAX_PROMPT_CODEPOINTS:
        raise ValueError(
            f"prompt must contain at most {MAX_PROMPT_CODEPOINTS} Unicode code points"
        )
    provenance = "benchmark-supported" if text == CANONICAL_PROMPT else "experimental"
    return Prompt(text=text, provenance=provenance)


def prompt_provenance_markup(value: str) -> str:
    """Render untrusted prompt text only after HTML escaping it."""
    prompt = classify_prompt(value)
    return (
        f'<p><span class="prompt-class">{prompt.provenance}</span> '
        f'<span class="prompt-text">{escape(prompt.text)}</span></p>'
    )
