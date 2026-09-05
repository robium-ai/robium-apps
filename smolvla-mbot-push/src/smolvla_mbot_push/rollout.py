"""Run a trained policy in the arena.

`lerobot-eval` resolves its environment from `--env.type`, which only covers
LeRobot's registered gym envs; this arena is not one, so the rollout loop is
ours. Evaluation runs locally: MPS is confirmed workable for inference, unlike
VLA *training*, which is not.

The policy owns an internal action-chunk queue, so `policy.reset()` must be
called between episodes or the first actions of a new episode are leftovers
predicted from the previous one's final frames.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch

from .config import CONTROL_HZ
from .record import TASK
from .sim import PushEnv
from .ui import Viewer


# The fine-tuned checkpoint inherits smolvla_base's three-camera config
# verbatim - fine-tuning never rewrites it - so inference has to apply the same
# mapping that training did.
DEFAULT_RENAME_MAP = {"observation.images.overhead": "observation.images.camera1"}


def _trained_rename_map(path: str) -> dict[str, str]:
    """The camera rename this checkpoint was actually trained with.

    Read from the checkpoint's own `train_config.json` rather than assumed,
    because it differs by policy: `lerobot/smolvla_base` inherits a three-camera
    layout (`camera1/2/3`) that fine-tuning never rewrites, so its datasets must
    be mapped onto it, while ACT builds its features from the dataset and needs
    no mapping at all. Applying SmolVLA's map to an ACT checkpoint renames the
    only camera to a key the policy is not looking for, and the policy is then
    handed no image - which looks like a policy that learned nothing.
    """
    import json

    config_path = Path(path) / "train_config.json"
    if config_path.exists():
        saved = json.loads(config_path.read_text()).get("rename_map")
        return saved or {}
    # An older checkpoint without a saved config is a SmolVLA one by history.
    return DEFAULT_RENAME_MAP


@dataclass
class RolloutConfig:
    policy_path: str
    dataset_repo_id: str
    dataset_root: Path | None = None
    episodes: int = 5
    steps: int = 300
    render_size: int = 256
    window: int = 640
    device: str = "mps"
    seed: int = 1000
    show: bool = True
    video_path: Path | None = None
    video_scale: int = 3
    rename_map: dict[str, str] | None = None
    # MuJoCo pauses while the policy thinks, so a 210ms forward pass costs the
    # simulated robot nothing: the block has not moved and the frame it planned
    # from is still true when the chunk lands. On hardware the world keeps
    # going. Charging inference its wall-clock cost is what makes the two
    # comparable - and it is the difference between a fast policy and a slow
    # one, not between a good policy and a bad one.
    realtime: bool = False
    # Charge a fixed cost per forward pass instead of the measured one. A
    # measurement is noisy and specific to this laptop; a fixed budget can be
    # swept, and can reproduce a latency this machine does not have.
    latency_ms: float | None = None
    # Drive a chunk, halt, let the robot come to rest, then look and plan again.
    # The clock keeps running through the halt and the plan - the robot is
    # stopped, not the world - which is exactly what the hardware does under
    # the same flag. Without this the two cannot be compared.
    stop_and_go: bool = False
    settle_seconds: float = 0.5
    # None keeps whatever the checkpoint trained with.
    n_action_steps: int | None = None


def load_policy(config: RolloutConfig):
    """Load a checkpoint together with its processor pipeline.

    The processors are not optional decoration: since 0.6 a checkpoint without
    `policy_preprocessor.json` / `policy_postprocessor.json` beside its weights
    cannot be loaded at all, and two checkpoints of the same family can encode
    different camera layouts.
    """
    from lerobot.configs.policies import PreTrainedConfig
    from lerobot.datasets.lerobot_dataset import LeRobotDatasetMetadata
    from lerobot.policies.factory import make_policy, make_pre_post_processors

    path = _local_checkpoint(config.policy_path)

    cfg = PreTrainedConfig.from_pretrained(path)
    cfg.pretrained_path = path
    cfg.device = config.device

    # How many of the chunk to execute before looking again is an inference
    # choice, not a trained one - the weights predict all `chunk_size` steps
    # either way. Raising it drives further on one look; the policy is blind
    # for the whole of it.
    if config.n_action_steps is not None:
        if config.n_action_steps > cfg.chunk_size:
            raise SystemExit(
                f"--n-action-steps {config.n_action_steps} exceeds the trained "
                f"chunk_size {cfg.chunk_size}: there are no more actions to run"
            )
        cfg.n_action_steps = config.n_action_steps

    meta = LeRobotDatasetMetadata(
        config.dataset_repo_id,
        root=str(config.dataset_root) if config.dataset_root else None,
    )
    rename_map = config.rename_map
    if rename_map is None:
        rename_map = _trained_rename_map(path)
    policy = make_policy(cfg, ds_meta=meta, rename_map=rename_map)
    # The saved preprocessor names its tokenizer by the relative path
    # "tokenizer", which is resolved against the working directory rather than
    # the checkpoint. Point it at the copy that ships inside the checkpoint.
    tokenizer_dir = Path(path) / "tokenizer"
    overrides: dict[str, dict] = {}
    if tokenizer_dir.is_dir():
        overrides["tokenizer_processor"] = {"tokenizer_name": str(tokenizer_dir)}
    # The processor also bakes in the device it was trained on - "cuda" for a
    # run on HF Jobs - which is not what we are evaluating on.
    overrides["device_processor"] = {"device": config.device}
    preprocessor, postprocessor = make_pre_post_processors(
        cfg, pretrained_path=path, preprocessor_overrides=overrides
    )
    policy.eval()
    return policy, preprocessor, postprocessor


def _local_checkpoint(policy_path: str) -> str:
    """Return a local directory for the checkpoint, downloading it if needed.

    The preprocessor config names its tokenizer by the relative path
    "tokenizer", which only resolves beside a checkpoint on disk. Handed a Hub
    id, the loader instead tries to resolve "tokenizer" as a model id and fails
    with a misleading "not a valid model identifier" error, so a Hub checkpoint
    has to be materialized locally first.
    """
    if Path(policy_path).is_dir():
        return policy_path

    from huggingface_hub import snapshot_download

    print(f"Downloading {policy_path} ...")
    return snapshot_download(
        repo_id=policy_path,
        # The training-state and per-step checkpoint copies are large and
        # irrelevant to inference.
        ignore_patterns=["checkpoints/*"],
    )


def _observation(frame: np.ndarray, state: np.ndarray, device: str) -> dict:
    """Shape one env frame the way the dataset presented it during training."""
    image = torch.from_numpy(frame).permute(2, 0, 1).float().div(255.0).unsqueeze(0)
    return {
        "observation.images.overhead": image.to(device),
        # Whatever the caller tracks, what the policy is handed must match what
        # it was trained on - and since `record` writes a constant, feeding the
        # previous action here would put it outside anything it has ever seen.
        "observation.state": torch.zeros(1, 2, device=device),
        "task": [TASK],
    }


def rollout(config: RolloutConfig) -> int:
    policy, preprocessor, postprocessor = load_policy(config)

    period_ms = 1000.0 / float(CONTROL_HZ)
    if config.realtime or config.latency_ms is not None:
        charged = f"{config.latency_ms:0.0f} ms" if config.latency_ms is not None else "measured"
        print(f"real time: the arena keeps moving while the policy thinks ({charged} per plan, "
              f"{period_ms:0.0f} ms per tick)")

    viewer = Viewer(size=config.window, title="rollout") if config.show else None
    writer = _VideoWriter(config) if config.video_path else None
    distances = []

    try:
        with PushEnv(render_size=config.render_size) as env:
            for episode in range(config.episodes):
                frame = env.reset(seed=config.seed + episode)
                state = np.zeros(2, dtype=np.float32)
                # Clear the chunk queue; otherwise this episode opens with
                # actions predicted from the previous episode's last frames.
                policy.reset()

                # select_action pops from a queue and only runs a forward pass
                # when it empties, so the cost falls on every n_action_steps-th
                # tick rather than being spread across them.
                n_action_steps = max(1, int(getattr(policy.config, "n_action_steps", 1)))
                held = np.zeros(2, dtype=np.float32)
                budget = config.steps
                step = 0

                stop = np.zeros(2, dtype=np.float32)
                settle_ticks = int(round(config.settle_seconds * CONTROL_HZ))

                def think(frame_now, state_now):
                    """One forward pass, and the ticks it costs the world."""
                    batch = preprocessor(_observation(frame_now, state_now, config.device))
                    began = time.perf_counter()
                    with torch.no_grad():
                        raw = policy.select_action(batch)
                    measured_ms = (time.perf_counter() - began) * 1000.0
                    act = postprocessor(raw).squeeze(0).float().cpu().numpy()
                    if config.latency_ms is not None:
                        cost = config.latency_ms
                    elif config.realtime:
                        cost = measured_ms
                    else:
                        cost = 0.0
                    return act, int(cost / period_ms)

                while budget > 0:
                    if config.stop_and_go:
                        # Halt and let the robot settle. The clock runs on.
                        for _ in range(min(settle_ticks, budget)):
                            frame = env.step(stop)
                            budget -= 1
                        if budget <= 0:
                            break
                        # Look and plan while standing still. Dropping the queue
                        # forces a real forward pass rather than a pop from a
                        # chunk built before the robot stopped.
                        policy.reset()
                        action, lag = think(frame, state)
                        for _ in range(min(lag, budget)):
                            frame = env.step(stop)
                            budget -= 1
                        # Drive the chunk out. Only the first tick cost a pass;
                        # the rest pop from the queue.
                        for i in range(n_action_steps):
                            if budget <= 0:
                                break
                            if i:
                                action, _ = think(frame, state)
                            frame = env.step(action)
                            budget -= 1
                            state = action.astype(np.float32)
                        continue

                    action, lag = think(frame, state)
                    lag = lag if step % n_action_steps == 0 or config.latency_ms is None else 0
                    # The ticks that elapse while the policy is thinking. The
                    # robot is not idle through them: like the hardware feeder,
                    # it keeps issuing the last command it was given.
                    for _ in range(min(lag, budget)):
                        frame = env.step(held)
                        budget -= 1
                    if budget <= 0:
                        break

                    frame = env.step(action)
                    budget -= 1
                    step += 1
                    held = action.astype(np.float32)
                    state = action.astype(np.float32)

                    lines = [
                        f"episode {episode + 1}/{config.episodes}   step {step + 1}",
                        f"throttle {action[0]:+0.2f}   steer {action[1]:+0.2f}",
                    ]
                    if viewer is not None:
                        viewer.show(frame, lines)
                    if writer is not None:
                        writer.add(frame)

                # Reported for orientation only. Nothing in training consumed it,
                # and with a handful of demonstrations it says little.
                distance = float(
                    np.linalg.norm(env.body_xy("block") - np.array([0.35, 0.0]))
                )
                distances.append(distance)
                print(f"episode {episode + 1}: block ended {distance:0.3f} m from the goal")
    finally:
        if viewer is not None:
            viewer.close()
        if writer is not None:
            writer.close()
            print(f"\nVideo written to {config.video_path}")

    print(f"\nmean final distance: {np.mean(distances):0.3f} m over {len(distances)} episode(s)")
    return 0


class _VideoWriter:
    """Write rollout frames to an mp4.

    Episodes are concatenated into one file so a single scrub covers the whole
    run, which is usually what you want when comparing successes to failures.
    """

    def __init__(self, config: RolloutConfig):
        import cv2

        self._cv2 = cv2
        size = config.render_size * config.video_scale
        config.video_path.parent.mkdir(parents=True, exist_ok=True)
        self._writer = cv2.VideoWriter(
            str(config.video_path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            float(CONTROL_HZ),
            (size, size),
        )
        self._size = size

    def add(self, frame: np.ndarray) -> None:
        cv2 = self._cv2
        view = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        view = cv2.resize(view, (self._size, self._size), interpolation=cv2.INTER_NEAREST)
        self._writer.write(view)

    def close(self) -> None:
        self._writer.release()
