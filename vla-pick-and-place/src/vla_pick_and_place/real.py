"""Lazy CUDA-only adapter for the pinned Pi0.5 checkpoint and LIBERO task."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from vla_pick_and_place.config import (
    CHECKPOINT_REVISION,
    MAX_STEPS,
    N_ACTION_STEPS,
    TASK_ID,
    TASK_NAME,
    TASK_SUITE,
    TOKENIZER_FILES,
    TOKENIZER_REVISION,
)
from vla_pick_and_place.rollout import EnvironmentStep, Observation, RolloutRunner

CHECKPOINT_ARTIFACT_FILES = (
    "config.json",
    "model.safetensors",
    "policy_preprocessor.json",
    "policy_preprocessor_step_2_normalizer_processor.safetensors",
    "policy_postprocessor.json",
    "policy_postprocessor_step_0_unnormalizer_processor.safetensors",
)
REQUIRED_CHECKPOINT_FILES = (
    *CHECKPOINT_ARTIFACT_FILES,
    *(f"tokenizer/{name}" for name in TOKENIZER_FILES),
    "tokenizer/REVISION",
)


def _batch_nested_arrays(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _batch_nested_arrays(item) for key, item in value.items()}
    if isinstance(value, np.ndarray):
        return np.expand_dims(value, axis=0)
    return value


def _batch_libero_robot_state(observation: dict[str, Any]) -> dict[str, Any]:
    """Copy and batch nested state from one direct, non-vectorized LIBERO env."""
    robot_state = observation.get("robot_state")
    if not isinstance(robot_state, Mapping):
        raise TypeError("LIBERO observation must contain nested robot_state")
    batched = observation.copy()
    batched["robot_state"] = _batch_nested_arrays(robot_state)
    return batched


def validate_checkpoint_snapshot(path: Path) -> None:
    revision_file = path / "REVISION"
    if (
        not revision_file.is_file()
        or revision_file.read_text().strip() != CHECKPOINT_REVISION
    ):
        raise RuntimeError(f"checkpoint REVISION must be {CHECKPOINT_REVISION}")
    tokenizer_revision = path / "tokenizer" / "REVISION"
    if (
        not tokenizer_revision.is_file()
        or tokenizer_revision.read_text().strip() != TOKENIZER_REVISION
    ):
        raise RuntimeError(f"tokenizer REVISION must be {TOKENIZER_REVISION}")
    missing = [
        name for name in REQUIRED_CHECKPOINT_FILES if not (path / name).is_file()
    ]
    if missing:
        raise RuntimeError(f"checkpoint snapshot is incomplete: {', '.join(missing)}")


def validate_tied_embedding(policy: Any) -> None:
    """Fail closed unless the PaliGemma input embedding shares head storage."""
    paligemma = policy.model.paligemma_with_expert.paligemma
    embedding = paligemma.model.language_model.embed_tokens.weight
    head = paligemma.lm_head.weight
    if embedding.data_ptr() != head.data_ptr():
        raise RuntimeError("PaliGemma embedding and language head are not tied")


class LiberoTaskEnvironment:
    def __init__(self) -> None:
        from lerobot.envs.libero import LiberoEnv
        from libero.libero import benchmark

        suite_type = benchmark.get_benchmark_dict()[TASK_SUITE]
        self.suite = suite_type()
        task = self.suite.get_task(TASK_ID)
        if task.name != TASK_NAME:
            raise RuntimeError(
                f"LIBERO task {TASK_ID} drifted: expected {TASK_NAME}, got {task.name}"
            )
        self.env = LiberoEnv(
            task_suite=self.suite,
            task_id=TASK_ID,
            task_suite_name=TASK_SUITE,
            episode_length=MAX_STEPS,
            observation_width=256,
            observation_height=256,
            visualization_width=640,
            visualization_height=480,
            obs_type="pixels_agent_pos",
            init_states=True,
            episode_index=0,
            n_envs=1,
        )

    @staticmethod
    def _observation(raw: dict[str, Any]) -> Observation:
        # LIBERO's recorded convention and LeRobot visualization both rotate
        # agentview by 180 degrees. Copy removes negative numpy strides.
        frame_array = raw["pixels"]["image"][::-1, ::-1].copy()
        return Observation(frame=Image.fromarray(frame_array), policy_input=raw)

    def reset(self, state_id: int, seed: int) -> Observation:
        self.env.init_state_id = state_id
        raw, _ = self.env.reset(seed=seed)
        return self._observation(raw)

    def step(self, action: Any) -> EnvironmentStep:
        raw, _reward, terminated, truncated, info = self.env.step(action)
        final_info = info.get("final_info", info)
        return EnvironmentStep(
            observation=self._observation(raw),
            success=bool(final_info.get("is_success", False)),
            done=bool(terminated or truncated),
        )


class Pi05PolicyAdapter:
    def __init__(self, checkpoint_path: Path) -> None:
        import torch
        from lerobot.configs.policies import PreTrainedConfig
        from lerobot.envs.configs import LiberoEnv as LiberoEnvConfig
        from lerobot.envs.factory import make_env_pre_post_processors
        from lerobot.policies.factory import make_pre_post_processors
        from lerobot.policies.pi05.modeling_pi05 import PI05Policy

        if not torch.cuda.is_available():
            raise RuntimeError("real Pi0.5 inference requires CUDA")
        validate_checkpoint_snapshot(checkpoint_path)
        config = PreTrainedConfig.from_pretrained(
            checkpoint_path, local_files_only=True
        )
        config.device = "cuda"
        config.n_action_steps = N_ACTION_STEPS
        self.policy = PI05Policy.from_pretrained(
            checkpoint_path,
            config=config,
            local_files_only=True,
            strict=False,
        )
        validate_tied_embedding(self.policy)
        self.preprocessor, self.postprocessor = make_pre_post_processors(
            policy_cfg=config,
            pretrained_path=str(checkpoint_path),
            preprocessor_overrides={
                "device_processor": {"device": "cuda"},
                "tokenizer_processor": {
                    "tokenizer_name": str(checkpoint_path / "tokenizer")
                },
            },
        )
        env_config = LiberoEnvConfig(
            task=TASK_SUITE,
            task_ids=[TASK_ID],
            episode_length=MAX_STEPS,
            observation_width=256,
            observation_height=256,
        )
        self.env_preprocessor, _ = make_env_pre_post_processors(env_config, config)
        self.torch = torch

    def reset(self) -> None:
        self.policy.reset()

    def select_action(self, observation: dict[str, Any], prompt: str):
        from lerobot.envs.utils import preprocess_observation

        batch = preprocess_observation(_batch_libero_robot_state(observation))
        batch["task"] = [prompt]
        batch = self.env_preprocessor(batch)
        batch = self.preprocessor(batch)
        with self.torch.inference_mode():
            action = self.policy.select_action(batch)
        action = self.postprocessor(action)
        return action.to("cpu").numpy()[0]


def build_real_runner() -> RolloutRunner:
    if os.environ.get("MUJOCO_GL") != "egl":
        raise RuntimeError("real headless runtime requires MUJOCO_GL=egl")
    checkpoint_path = Path(
        os.environ.get("VLA_CHECKPOINT_PATH", "/models/pi05-libero-v044")
    )
    return RolloutRunner(
        LiberoTaskEnvironment(), Pi05PolicyAdapter(checkpoint_path), max_steps=MAX_STEPS
    )
