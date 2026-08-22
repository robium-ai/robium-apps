"""Official-checkpoint pass-bar smoke test.

One command: ``uv run pytest tests/test_smoke.py``

The smoke path never trains. It proves that the pinned official LeRobot
checkpoint is present with auditable compatibility files, then runs one full
PushT episode through the real Diffusion Policy on the best local device.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from diffusion_policy_pusht import config  # noqa: E402
from diffusion_policy_pusht.official import ensure_official_checkpoint  # noqa: E402
from diffusion_policy_pusht.rollout import (  # noqa: E402
    MAX_EPISODE_STEPS,
    DiffusionCheckpoint,
)


def test_official_checkpoint_is_auditable_and_loadable():
    checkpoint = ensure_official_checkpoint()
    for name in (
        "config.json",
        "model.safetensors",
        "policy_preprocessor.json",
        "policy_postprocessor.json",
        "eval_info.json",
        "robium-provenance.json",
    ):
        assert (checkpoint / name).is_file(), f"missing {name} in {checkpoint}"

    provenance = json.loads((checkpoint / "robium-provenance.json").read_text())
    assert provenance["repo_id"] == config.OFFICIAL_MODEL_ID
    assert provenance["revision"] == config.OFFICIAL_MODEL_REVISION
    assert provenance["processor_conversion"]["weights_modified"] is False
    assert provenance["processor_conversion"]["dataset_stats"] == config.DATASET_REPO_ID


def test_official_fast_mode_completes_real_episode():
    checkpoint = DiffusionCheckpoint(
        ensure_official_checkpoint(),
        device=config.demo_device(),
    )
    checkpoint.configure(n_action_steps=8, num_inference_steps=10)
    result = checkpoint.run(seed=config.BENCHMARK_SEEDS[0], shape="T")

    assert result.steps == MAX_EPISODE_STEPS
    assert 0.0 <= result.max_coverage <= 1.0
    assert result.max_coverage > 0.1, "policy rollout made no meaningful contact"
    assert result.sum_reward > 0.0
    assert result.elapsed_s > 0.0
    assert not result.aborted
    print(
        "\nOFFICIAL FAST SMOKE: "
        f"device={checkpoint.device} success={result.success} "
        f"max_coverage={result.max_coverage:.3f} elapsed={result.elapsed_s:.1f}s"
    )
