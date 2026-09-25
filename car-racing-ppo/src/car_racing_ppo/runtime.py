from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import gymnasium as gym
import numpy as np
from huggingface_hub import hf_hub_download, try_to_load_from_cache
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv, VecFrameStack, VecTransposeImage

MODEL_REPO = "pableitorr/ppo-CarRacing-v2"
MODEL_REVISION = "a3d30ae5f460c866df89364e14ceee7e9f5949ce"
MODEL_FILENAME = "ppo-CarRacing-v2.zip"
MODEL_SHA256 = "edb9a2d98c51172c3723d2b1cc2a752a4c3832f14a3d2b1200297f4d4ea763ca"
FRAME_SKIP = 2
FRAME_STACK = 2
IMAGE_SIZE = 64


class FrameSkip(gym.Wrapper):
    """Exact action-repeat wrapper used by RL Baselines3 Zoo v2.3.0."""

    def __init__(self, env: gym.Env, skip: int = FRAME_SKIP):
        super().__init__(env)
        self._skip = skip

    def step(self, action):
        total_reward = 0.0
        for _ in range(self._skip):
            observation, reward, terminated, truncated, info = self.env.step(action)
            total_reward += float(reward)
            if terminated or truncated:
                break
        return observation, total_reward, terminated, truncated, info


class EvidenceWrapper(gym.Wrapper):
    """Expose track progress before DummyVecEnv automatically resets an episode."""

    def step(self, action):
        observation, reward, terminated, truncated, info = self.env.step(action)
        raw_env = self.env.unwrapped
        info = dict(info)
        info["track_tiles"] = len(raw_env.track)
        info["visited_tiles"] = raw_env.tile_visited_count
        return observation, reward, terminated, truncated, info


def _sha256(file_path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(file_path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cached_checkpoint() -> str | None:
    cached = try_to_load_from_cache(
        MODEL_REPO,
        MODEL_FILENAME,
        revision=MODEL_REVISION,
    )
    return cached if isinstance(cached, str) else None


def fetch_checkpoint() -> str:
    checkpoint = hf_hub_download(
        repo_id=MODEL_REPO,
        filename=MODEL_FILENAME,
        revision=MODEL_REVISION,
    )
    actual = _sha256(checkpoint)
    if actual != MODEL_SHA256:
        raise RuntimeError(
            f"Checkpoint checksum mismatch: expected {MODEL_SHA256}, got {actual}"
        )
    return checkpoint


def make_vec_env(render_mode: str | None, seed: int):
    def make_env():
        env = gym.make("CarRacing-v2", render_mode=render_mode)
        env = FrameSkip(env, skip=FRAME_SKIP)
        env = gym.wrappers.ResizeObservation(env, IMAGE_SIZE)
        env = gym.wrappers.GrayScaleObservation(env, keep_dim=True)
        env = EvidenceWrapper(env)
        return env

    env = DummyVecEnv([make_env])
    env = VecTransposeImage(env)
    env = VecFrameStack(env, n_stack=FRAME_STACK)
    env.seed(seed)
    return env


def load_policy(env) -> tuple[PPO, str]:
    checkpoint = fetch_checkpoint()
    model = PPO.load(checkpoint, env=env, device="cpu")
    return model, checkpoint


@dataclass
class EpisodeResult:
    seed: int
    track_tiles: int
    track_sha256: str
    visited_tiles: int
    track_completion_percent: float
    policy_steps: int
    simulated_frames: int
    wall_seconds: float
    policy_steps_per_second: float
    simulated_fps: float
    reward: float
    ended: bool
    truncated: bool
    outcome: str


def run_episode(
    *,
    seed: int,
    render: bool,
    max_policy_steps: int | None = None,
) -> EpisodeResult:
    env = make_vec_env("human" if render else "rgb_array", seed)
    model, _ = load_policy(env)
    # PPO.load() restores the checkpoint's training seed and applies it to the
    # attached VecEnv. Reapply the requested evaluation seed afterwards so
    # different --seed values actually generate different tracks.
    env.seed(seed)
    observation = env.reset()
    overlay_state = _install_overlay(env) if render else None
    raw_env = _raw_env(env)
    track_tiles = len(raw_env.track)
    track_sha256 = hashlib.sha256(repr(raw_env.track).encode()).hexdigest()[:16]
    visited_tiles = raw_env.tile_visited_count
    total_reward = 0.0
    started = time.perf_counter()
    steps = 0
    ended = False
    truncated = False

    try:
        while max_policy_steps is None or steps < max_policy_steps:
            if render and _poll_stop():
                break
            action, _ = model.predict(observation, deterministic=True)
            if overlay_state is not None:
                elapsed = max(time.perf_counter() - started, 1e-9)
                overlay_state.update(
                    action=np.asarray(action[0]),
                    reward=total_reward,
                    steps=steps + 1,
                    rate=(steps + 1) / elapsed,
                )
            observation, rewards, dones, infos = env.step(action)
            steps += 1
            total_reward += float(rewards[0])
            visited_tiles = int(infos[0]["visited_tiles"])

            if bool(dones[0]):
                ended = True
                truncated = bool(infos[0].get("TimeLimit.truncated", False))
                break
    finally:
        env.close()

    elapsed = max(time.perf_counter() - started, 1e-9)
    simulated_frames = steps * FRAME_SKIP
    completion = round(100.0 * visited_tiles / track_tiles, 1)
    if completion >= 100.0:
        outcome = "lap_complete"
    elif ended and truncated:
        outcome = "time_limit"
    elif ended:
        outcome = "terminated"
    else:
        outcome = "stopped"
    return EpisodeResult(
        seed=seed,
        track_tiles=track_tiles,
        track_sha256=track_sha256,
        visited_tiles=visited_tiles,
        track_completion_percent=completion,
        policy_steps=steps,
        simulated_frames=simulated_frames,
        wall_seconds=round(elapsed, 3),
        policy_steps_per_second=round(steps / elapsed, 1),
        simulated_fps=round(simulated_frames / elapsed, 1),
        reward=round(total_reward, 2),
        ended=ended,
        truncated=truncated,
        outcome=outcome,
    )


def _raw_env(env):
    base = env
    while hasattr(base, "venv"):
        base = base.venv
    return base.envs[0].unwrapped


def _poll_stop() -> bool:
    import pygame

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            return True
        elif event.type == pygame.KEYDOWN and event.key in (pygame.K_q, pygame.K_ESCAPE):
            return True
    return False


def _install_overlay(env) -> dict[str, Any]:
    raw_env = _raw_env(env)
    state: dict[str, Any] = {
        "action": np.zeros(3, dtype=np.float32),
        "reward": 0.0,
        "steps": 0,
        "rate": 0.0,
    }
    original_render = raw_env._render

    def render_with_overlay(mode: str):
        result = original_render(mode)
        if mode == "human" and raw_env.screen is not None:
            _paint_overlay(raw_env.screen, **state)
        return result

    raw_env._render = render_with_overlay
    return state


def _paint_overlay(screen, *, action: np.ndarray, reward: float, steps: int, rate: float) -> None:
    import pygame

    panel = pygame.Surface((360, 118), pygame.SRCALPHA)
    panel.fill((8, 12, 18, 215))
    font = pygame.font.Font(None, 25)
    small = pygame.font.Font(None, 21)
    lines = [
        (font, "PRETRAINED PPO  •  AUTONOMOUS", (120, 220, 255)),
        (
            small,
            f"steer {action[0]:+0.2f}   gas {action[1]:0.2f}   brake {action[2]:0.2f}",
            (245, 245, 245),
        ),
        (
            small,
            f"reward {reward:0.1f}   decisions {steps}   policy {rate:0.1f} Hz",
            (220, 220, 220),
        ),
        (small, "Q / Esc to stop", (165, 175, 185)),
    ]
    y = 10
    for line_font, text, color in lines:
        panel.blit(line_font.render(text, True, color), (12, y))
        y += 27
    screen.blit(panel, (12, 12))
    pygame.display.flip()


def run_check(*, episodes: int, first_seed: int) -> dict[str, Any]:
    results = [
        run_episode(seed=first_seed + index, render=False)
        for index in range(episodes)
    ]
    rewards = [result.reward for result in results]
    fps_values = [result.simulated_fps for result in results]
    evidence = {
        "model": {
            "repo": MODEL_REPO,
            "revision": MODEL_REVISION,
            "filename": MODEL_FILENAME,
            "sha256": MODEL_SHA256,
        },
        "runtime": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
            "device": "cpu",
        },
        "preprocessing": {
            "frame_skip": FRAME_SKIP,
            "image_size": IMAGE_SIZE,
            "grayscale": True,
            "frame_stack": FRAME_STACK,
        },
        "episodes": [asdict(result) for result in results],
        "aggregate": {
            "episodes": episodes,
            "mean_reward": round(float(np.mean(rewards)), 2),
            "reward_std": round(float(np.std(rewards)), 2),
            "mean_simulated_fps": round(float(np.mean(fps_values)), 1),
        },
    }
    output_dir = Path("outputs")
    output_dir.mkdir(exist_ok=True)
    (output_dir / "last-check.json").write_text(
        json.dumps(evidence, indent=2) + "\n",
        encoding="utf-8",
    )
    return evidence
