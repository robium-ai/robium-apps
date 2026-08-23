"""Load and query the migrated ACT policy."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import torch
from lerobot.configs.policies import PreTrainedConfig
from lerobot.envs.utils import preprocess_observation
from lerobot.policies.act.modeling_act import ACTPolicy
from lerobot.policies.factory import make_pre_post_processors

from act_aloha_cube_transfer import config


def preferred_device() -> str:
    return "mps" if torch.backends.mps.is_available() else "cpu"


class ACTCheckpoint:
    def __init__(self, path: str | Path, device: str | None = None):
        self.path = Path(path).resolve()
        missing = [
            name
            for name in (
                "config.json",
                "model.safetensors",
                "policy_preprocessor.json",
                "policy_postprocessor.json",
                "manifest.json",
            )
            if not (self.path / name).is_file()
        ]
        if missing:
            raise FileNotFoundError(f"checkpoint {self.path} is missing: {', '.join(missing)}")

        policy_cfg = PreTrainedConfig.from_pretrained(self.path)
        if policy_cfg.type != "act":
            raise ValueError(f"checkpoint is {policy_cfg.type!r}, expected 'act'")
        policy_cfg.device = device or preferred_device()
        self.device = policy_cfg.device
        self.policy = ACTPolicy.from_pretrained(self.path, config=policy_cfg)
        self.policy.eval()
        self.preprocessor, self.postprocessor = make_pre_post_processors(
            policy_cfg=policy_cfg,
            pretrained_path=str(self.path),
            preprocessor_overrides={"device_processor": {"device": self.device}},
        )

    @property
    def chunk_size(self) -> int:
        return int(self.policy.config.chunk_size)

    def reset(self) -> None:
        self.policy.reset()

    def predict_chunk(self, observation: dict) -> np.ndarray:
        """Predict the complete 100-action chunk for one environment observation."""
        self.policy.reset()
        batch = self.preprocessor(preprocess_observation(observation))
        with torch.inference_mode():
            chunk = self.policy.predict_action_chunk(batch)
        chunk = self.postprocessor(chunk)
        actions = chunk.squeeze(0).detach().cpu().numpy().astype(np.float32)
        expected = (config.ACTION_CHUNK_SIZE, 14)
        if actions.shape != expected or not np.isfinite(actions).all():
            raise ValueError(f"ACT returned invalid action chunk {actions.shape}; expected {expected}")
        return actions
