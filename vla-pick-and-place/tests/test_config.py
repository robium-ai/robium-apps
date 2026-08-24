import pytest

from vla_pick_and_place.config import (
    CANONICAL_PROMPT,
    CHECKPOINT_REVISION,
    CURATED_STATES,
    LEROBOT_REVISION,
    LIBERO_REVISION,
    PUBLICATION_EPISODES,
    TASK_ID,
    TASK_NAME,
    TASK_SUITE,
    classify_prompt,
    prompt_provenance_markup,
)


def test_upstream_and_task_pins_are_exact():
    assert CHECKPOINT_REVISION == "8e174154ef5f6c60a8da12ae99c303d8963138c1"
    assert LEROBOT_REVISION == "8fff0fde7c79f23a93d845d1a50e985de01f8b8a"
    assert LIBERO_REVISION == "8f1084e3132a39270c3a13ebe37270a43ece2a01"
    assert (TASK_SUITE, TASK_ID, TASK_NAME) == (
        "libero_goal",
        8,
        "put_the_bowl_on_the_plate",
    )


def test_curated_and_publication_state_mapping_is_fixed():
    assert [state.state_id for state in CURATED_STATES] == [0, 1, 2]
    assert [(episode.state_id, episode.seed) for episode in PUBLICATION_EPISODES] == [
        (state_id, 1000 + state_id) for state_id in range(20)
    ]


def test_prompt_classification_and_limits():
    assert CANONICAL_PROMPT == "put the bowl on the plate"
    canonical = classify_prompt(f"  {CANONICAL_PROMPT}\n")
    assert canonical.text == CANONICAL_PROMPT
    assert canonical.provenance == "benchmark-supported"

    edited = classify_prompt("put the blue bowl on the plate")
    assert edited.provenance == "experimental"

    with pytest.raises(ValueError, match="nonempty"):
        classify_prompt("  \n")
    with pytest.raises(ValueError, match="200"):
        classify_prompt("x" * 201)


def test_prompt_rendering_escapes_html():
    markup = prompt_provenance_markup('<script>alert("x")</script>')
    assert "<script>" not in markup
    assert "&lt;script&gt;" in markup
