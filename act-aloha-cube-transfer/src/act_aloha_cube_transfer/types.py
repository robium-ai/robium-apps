from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np


@dataclass(frozen=True)
class RolloutStep:
    step: int
    total: int
    frame: np.ndarray
    state: np.ndarray
    action: np.ndarray | None
    reward: float
    phase: str
    policy_call: int
    chunk_index: int
    inference_s: float
    done: bool = False
    success: bool = False
    aborted: bool = False


@dataclass(frozen=True)
class RolloutResult:
    seed: int
    execution_horizon: int
    success: bool
    aborted: bool
    steps: int
    policy_calls: int
    max_reward: float
    sum_reward: float
    elapsed_s: float
    inference_seconds: tuple[float, ...]

    def to_dict(self) -> dict:
        return asdict(self)
