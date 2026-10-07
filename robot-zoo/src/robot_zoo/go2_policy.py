"""Pinned Go2 MoE/CTS inference adapter; no training or hand-authored gait.

Observation, PD gains and actuator dynamics follow wty-yy/go2_rl_gym.
See docs/go2-controller.md and GO2_POLICY_LICENSE.txt for provenance.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import urllib.request

import numpy as np

REVISION = "30e74dc507bec7a642a8c98be26081f2c6f0822d"
POLICY_NAME = "go2_moe_cts_high_slope_thre_164k_0.6715.pt"
POLICY_SHA256 = "9d9ad783a1017b6eced5984eb95279cc5b36db8cc84d21e646f46ba2a8023d9d"
POLICY_URL = f"https://raw.githubusercontent.com/wty-yy/go2_rl_gym/{REVISION}/deploy/pre_train/go2/{POLICY_NAME}"
DEFAULT_ANGLES = np.array(
    [.1, .8, -1.5, -.1, .8, -1.5, .1, 1., -1.5, -.1, 1., -1.5],
    dtype=np.float32,
)


def policy_path() -> Path:
    """Cache exactly the reviewed upstream artifact, verifying before loading."""
    directory = Path.home() / ".cache" / "robot-zoo" / REVISION
    destination = directory / POLICY_NAME
    if destination.exists() and hashlib.sha256(destination.read_bytes()).hexdigest() == POLICY_SHA256:
        return destination
    directory.mkdir(parents=True, exist_ok=True)
    print("Downloading Go2 walking policy (5.2 MB)…", flush=True)
    with urllib.request.urlopen(POLICY_URL, timeout=60) as response:
        content = response.read(6_000_000)
    if hashlib.sha256(content).hexdigest() != POLICY_SHA256:
        raise RuntimeError("Go2 policy checksum mismatch; refusing to load it")
    with tempfile.NamedTemporaryFile(dir=directory, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(content)
    temporary.replace(destination)
    return destination


class Go2Policy:
    def __init__(self):
        import torch
        self.torch = torch
        torch.set_num_threads(1)
        self.network = torch.jit.load(str(policy_path()), map_location="cpu").eval()
        self.reset()

    def reset(self):
        # This export keeps history as an attribute, not a registered buffer.
        with self.torch.inference_mode():
            self.network.history.zero_()
        self.previous_action = np.zeros(12, dtype=np.float32)

    def target(self, data, command: np.ndarray) -> np.ndarray:
        w, x, y, z = data.qpos[3:7]
        gravity = [2 * (-z*x + w*y), -2 * (z*y + w*x), 1 - 2 * (w*w + z*z)]
        observation = np.concatenate([
            data.qvel[3:6] * .25, gravity, command * [2., 2., .25],
            data.qpos[7:] - DEFAULT_ANGLES, data.qvel[6:] * .05,
            self.previous_action,
        ]).astype(np.float32)
        with self.torch.inference_mode():
            action, _ = self.network(self.torch.from_numpy(observation).unsqueeze(0))
            self.previous_action = action.numpy().reshape(12).copy()
        if not np.isfinite(self.previous_action).all():
            raise RuntimeError("Go2 policy returned non-finite actions")
        return DEFAULT_ANGLES + .25 * self.previous_action
