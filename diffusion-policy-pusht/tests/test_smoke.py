"""Official-checkpoint pass-bar smoke test.

One command: ``uv run pytest tests/test_smoke.py``

The smoke path never trains. It proves that the pinned official LeRobot
checkpoint is present with auditable compatibility files, then runs one full
PushT episode through the real Diffusion Policy on the best local device.
"""

import json
import os
import sys

import torch
from safetensors.torch import load_file

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from diffusion_policy_pusht import config  # noqa: E402
from diffusion_policy_pusht.official import (  # noqa: E402
    POSTPROCESSOR_STATE,
    PREPROCESSOR_STATE,
    ensure_official_checkpoint,
    legacy_normalization_stats,
)
from diffusion_policy_pusht.rollout import (  # noqa: E402
    MAX_EPISODE_STEPS,
    DiffusionCheckpoint,
    make_env,
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
    assert provenance["processor_conversion"]["version"] == 2
    assert "model.safetensors" in provenance["processor_conversion"]["stats_source"]

    processor_state = load_file(checkpoint / PREPROCESSOR_STATE)
    postprocessor_state = load_file(checkpoint / POSTPROCESSOR_STATE)
    for feature, values in legacy_normalization_stats(checkpoint).items():
        for stat, expected in values.items():
            assert torch.equal(processor_state[f"{feature}.{stat}"], expected)
    for stat, expected in legacy_normalization_stats(checkpoint)["action"].items():
        assert torch.equal(postprocessor_state[f"action.{stat}"], expected)

    benchmark_env = make_env("T")
    ood_env = make_env("Z")
    try:
        benchmark_env.reset(seed=config.OFFICIAL_EVAL_SEEDS[0])
        ood_env.reset(seed=config.OFFICIAL_EVAL_SEEDS[0])
        assert benchmark_env.unwrapped.__class__.__module__ == "gym_pusht.envs.pusht"
        assert benchmark_env.unwrapped.block.moment == 3000.0
        assert ood_env.unwrapped.__class__.__name__ == "PushShapeEnv"
    finally:
        benchmark_env.close()
        ood_env.close()


def test_official_fast_mode_completes_real_episode():
    checkpoint = DiffusionCheckpoint(
        ensure_official_checkpoint(),
        device=config.demo_device(),
    )
    checkpoint.configure(n_action_steps=8, num_inference_steps=10)
    result = checkpoint.run(seed=config.OFFICIAL_EVAL_SEEDS[0], shape="T")

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
