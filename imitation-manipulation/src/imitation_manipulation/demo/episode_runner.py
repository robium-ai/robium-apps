"""One-episode runner — the piece between the Gradio UI and the trained rungs.

Runs one policy rollout per call in a fresh env (construction is milliseconds
and guarantees no state leaks between runs). The env is the PushShape variant
of PushT: `shape="T"` is exactly the training distribution; L/I/Z are
out-of-distribution probes — the policy only ever saw T pixels, so these
show what (whether) the checkpoints generalize.

Policies load lazily per rung (ACT is ~200 MB on disk, seconds to load) and
stay cached; boot loads only the default rung so startup is fast.

The inference path is the same contract lerobot's own eval loop uses
(verified against lerobot 0.6.0's scripts/lerobot_eval.py rollout()):
preprocess_observation -> preprocessor pipeline -> policy.select_action ->
postprocessor pipeline. Single sync env — immune to the forkserver/async-env
gotcha by construction.
"""

import itertools
import json
import threading
from dataclasses import dataclass

import gymnasium as gym
import numpy as np
import rerun as rr
import torch
from lerobot.envs.utils import preprocess_observation

from imitation_manipulation import config, shapes

MAX_EPISODE_STEPS = 300  # gym_pusht registration default; lerobot's PushtEnv config agrees


def _log_step(rec: rr.RecordingStream, step: int, obs: dict, action, reward: float, max_reward: float) -> None:
    rec.set_time("step", sequence=step)
    # obs["pixels"] is the 96x96 frame the policy actually sees — honest by
    # construction. JPEG q85: tiny over the browser stream, fine to look at.
    rec.log("sim", rr.Image(obs["pixels"]).compress(jpeg_quality=85))
    rec.log("reward/coverage", rr.Scalars([float(reward)]))
    rec.log("reward/max_so_far", rr.Scalars([float(max_reward)]))
    rec.log("action/x", rr.Scalars([float(action[0])]))
    rec.log("action/y", rr.Scalars([float(action[1])]))


@dataclass
class StepEvent:
    step: int
    total: int
    done: bool = False
    success: bool = False
    max_reward: float = 0.0


class EpisodeRunner:
    """Owns the rung policies; serializes runs with a lock."""

    def __init__(self, device: str | None = None):
        self.device = device or config.demo_device()
        self.manifest = json.loads(config.DEMO_LADDER_MANIFEST.read_text())
        self.rungs = {r["name"]: r for r in self.manifest["rungs"]}
        self._policies: dict[str, tuple] = {}
        self._lock = threading.Lock()
        self._seed_counter = itertools.count()

        self._load(config.DEMO_DEFAULT_RUNG)  # boot cost: one rung, not four
        # Boot probe: prove the env constructs + renders in this process.
        probe = self._make_env(config.DEMO_DEFAULT_SHAPE)
        probe.reset(seed=0)
        probe.close()

    @staticmethod
    def _make_env(shape: str):
        return gym.make(
            shapes.ENV_ID, shape=shape, obs_type="pixels_agent_pos", render_mode="rgb_array"
        )

    def _load(self, rung: str) -> tuple:
        if rung not in self._policies:
            from lerobot.policies.act.modeling_act import ACTPolicy
            from lerobot.policies.factory import make_pre_post_processors

            path = str(config.APP_ROOT / self.rungs[rung]["checkpoint"])
            policy = ACTPolicy.from_pretrained(path)
            policy.to(self.device)
            policy.eval()
            pre, post = make_pre_post_processors(
                policy_cfg=policy.config,
                pretrained_path=path,
                preprocessor_overrides={"device_processor": {"device": self.device}},
            )
            self._policies[rung] = (policy, pre, post)
        return self._policies[rung]

    @property
    def busy(self) -> bool:
        return self._lock.locked()

    def run(self, rung: str, rec: rr.RecordingStream, shape: str = "T"):
        """Generator: one episode, yielding a StepEvent after each step."""
        if rung not in self.rungs:
            raise ValueError(f"unknown rung {rung!r}")
        if shape not in shapes.SHAPES:
            raise ValueError(f"unknown shape {shape!r}; choose from {list(shapes.SHAPES)}")
        # Wait, don't fail: a finishing predecessor releases within one step.
        if not self._lock.acquire(timeout=30):
            raise RuntimeError("a run is already in progress")
        try:
            yield from self._run_locked(rung, shape, rec)
        finally:
            self._lock.release()

    def _run_locked(self, rung: str, shape: str, rec: rr.RecordingStream):
        policy, pre, post = self._load(rung)
        policy.reset()
        # Fresh seed per run so repeat runs show different starts; offset from
        # the eval SEED so the demo never replays the gallery's exact episodes.
        seed = config.SEED + 10_000 + next(self._seed_counter)

        env = self._make_env(shape)
        try:
            obs, _ = env.reset(seed=seed)
            success = False
            max_reward = 0.0
            step = 0
            for step in range(MAX_EPISODE_STEPS):
                batch = pre(preprocess_observation(obs))
                with torch.inference_mode():
                    action = policy.select_action(batch)
                action = post(action)
                action = action.squeeze(0).cpu().numpy().astype(np.float32)

                obs, reward, terminated, truncated, info = env.step(action)
                max_reward = max(max_reward, float(reward))
                success = bool(info["is_success"])
                _log_step(rec, step, obs, action, float(reward), max_reward)
                yield StepEvent(step=step, total=MAX_EPISODE_STEPS, max_reward=max_reward)
                if terminated or truncated:
                    break

            yield StepEvent(step=step, total=MAX_EPISODE_STEPS, done=True,
                            success=success, max_reward=max_reward)
        finally:
            env.close()
