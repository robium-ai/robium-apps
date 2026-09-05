"""Record teleoperated episodes into a LeRobotDataset.

`lerobot-record` drives real robots over its own teleoperation stack and cannot
see a custom simulator, so the loop is hand-rolled. The one thing that must not
be skipped is `finalize()`: the CLI calls it for you, and a hand-rolled loop
that forgets it leaves a dataset that looks written but will not load.

What lands in each frame, per control tick:

    observation.images.overhead   the frame as it looked before you acted
    observation.state             constant zero - see below
    action                        the action you command now

`observation.state` is a constant, not the previous action. This arena's robot
has no encoders, so the last command is the only proprioception available - and
handing that to a behaviour-cloning policy is a trap. At 10 Hz two consecutive
teleop commands are nearly identical, so `action_t ~= state_t` fits the training
set almost perfectly with the image ignored entirely.

That is not hypothetical. The real-robot sibling app shipped exactly this
layout, trained to 0.033 loss, and produced a policy whose output sat 0.031 from
the previous action it was handed: varying the image moved its predictions by
0.149 while varying the state moved them by 0.279 and 0.580. On the robot it
drove a repeating pattern and never approached the block.

The feature stays in the dataset rather than being removed because SmolVLA's
`prepare_state` indexes `batch["observation.state"]` with no fallback, so a
dataset without the key raises KeyError on the first forward pass. A constant
carries no information, which is the whole point, and normalization is safe on
one because the normalizer divides by `std + eps`.

The action is the stick, not the wheels: what a policy learns to predict is
forward speed and turn rate, and `config.mix` turns those into wheel speeds
afterwards - identically at record time and at rollout time.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .config import CONTROL_HZ
from .sim import PushEnv
from .ui import Teleop, Viewer

TASK = "push the block onto the green square"

# See the note where this is written into each frame.
_NO_STATE = np.zeros(2, dtype=np.float32)

# A hand-driven episode that runs this long is a failed one; stop it rather than
# filling the dataset with a minute of aimless driving.
MAX_EPISODE_SECONDS = 60.0


@dataclass
class RecordConfig:
    repo_id: str
    root: Path
    episodes: int = 5
    render_size: int = 256
    window: int = 640
    push_to_hub: bool = False
    private: bool = False
    resume: bool = False


def _build_features(render_size: int) -> dict:
    return {
        "observation.images.overhead": {
            "dtype": "video",
            "shape": (render_size, render_size, 3),
            "names": ["height", "width", "channels"],
        },
        "observation.state": {
            "dtype": "float32",
            "shape": (2,),
            "names": ["throttle", "steer"],
        },
        "action": {
            "dtype": "float32",
            "shape": (2,),
            "names": ["throttle", "steer"],
        },
    }


def record(config: RecordConfig) -> int:
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    existing = 0
    if config.resume:
        if not config.root.exists():
            print(f"Nothing to resume at {config.root}.")
            return 1
        dataset = LeRobotDataset.resume(config.repo_id, root=str(config.root))
        existing = dataset.num_episodes
        print(f"Resuming {config.root} with {existing} episode(s) already recorded.")
    elif config.root.exists():
        print(
            f"{config.root} already exists.\n"
            "  Add to it with --resume, or pick another --root."
        )
        return 1
    else:
        dataset = LeRobotDataset.create(
            repo_id=config.repo_id,
            fps=int(CONTROL_HZ),
            features=_build_features(config.render_size),
            root=str(config.root),
            robot_type="diffdrive",
        )

    viewer = Viewer(size=config.window, title="record")
    teleop = Teleop()
    period = 1.0 / CONTROL_HZ
    max_frames = int(MAX_EPISODE_SECONDS * CONTROL_HZ)

    print(f"Recording {config.episodes} episode(s) with {teleop.source}.")
    print("  space  start / stop an episode")
    print("  r      discard the episode in progress and start it over")
    print("  q      quit")

    saved = 0
    try:
        with PushEnv(render_size=config.render_size) as env:
            while saved < config.episodes:
                outcome = _record_one(
                    env, dataset, viewer, teleop, period, max_frames, saved, config.episodes
                )
                if outcome == "quit":
                    break
                if outcome == "saved":
                    saved += 1
                    print(f"  episode {saved}/{config.episodes} saved")
    finally:
        teleop.close()
        viewer.close()

    if saved == 0 and existing == 0:
        print("No episodes recorded; discarding the empty dataset.")
        shutil.rmtree(config.root, ignore_errors=True)
        return 1

    # Quitting early keeps whatever was already saved: every episode is written
    # when you stop it, not in one batch at the end.
    dataset.finalize()
    total = existing + saved
    print(f"Finalized {total} episode(s) at {config.root}")
    if saved < config.episodes:
        print(f"  ({saved} of {config.episodes} recorded this session)")
        print(f"  Add more later:  ./app record --repo-id {config.repo_id} --resume")

    if config.push_to_hub:
        return push(config.repo_id, config.root, private=config.private)
    print(f"  Upload later:    ./app push --repo-id {config.repo_id}")
    return 0


def push(repo_id: str, root: Path, private: bool = False) -> int:
    """Upload an already-recorded local dataset to the Hub."""
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    if not root.exists():
        print(f"No dataset at {root}.")
        return 1

    dataset = LeRobotDataset(repo_id, root=str(root))
    print(f"Pushing {dataset.num_episodes} episode(s) to {repo_id} ...")
    dataset.push_to_hub(private=private, tags=["lerobot", "mujoco", "push"])
    print(f"  https://huggingface.co/datasets/{repo_id}")
    return 0


def _record_one(
    env: PushEnv,
    dataset,
    viewer: Viewer,
    teleop: Teleop,
    period: float,
    max_frames: int,
    saved: int,
    total: int,
) -> str:
    """Run one episode. Returns 'saved', 'discarded', or 'quit'."""
    import time

    import pygame

    env.reset()
    frame = env.observe()
    recording = False
    frames = 0
    last_action = np.zeros(2, dtype=np.float32)

    while True:
        started = time.monotonic()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "quit"
            if event.type != pygame.KEYDOWN:
                continue
            if event.key == pygame.K_q:
                return "quit"
            if event.key == pygame.K_r:
                # Drop whatever was buffered; the episode never happened.
                dataset.clear_episode_buffer()
                return "discarded"
            if event.key == pygame.K_SPACE:
                if not recording:
                    recording = True
                else:
                    if frames == 0:
                        return "discarded"
                    dataset.save_episode()
                    return "saved"

        action = teleop.read(period)

        if recording:
            dataset.add_frame(
                {
                    "observation.images.overhead": frame,
                    # Deliberately constant. The obvious thing to put here is
                    # the previous action - it is the only proprioception a
                    # chassis without encoders has - and it is a trap. At 10 Hz
                    # two consecutive teleop commands are nearly identical, so
                    # `action_t ~= state_t` predicts the training set almost
                    # perfectly and a policy can reach a very low loss without
                    # ever looking at the image. Measured on the real sibling
                    # app, a policy trained that way tracked its own previous
                    # action to within 0.031 and drove the robot in circles.
                    # A constant carries no information, which is the point; the
                    # feature stays because SmolVLA indexes it unconditionally.
                    "observation.state": _NO_STATE,
                    "action": action.astype(np.float32),
                    "task": TASK,
                }
            )
            frames += 1

        frame = env.step(action)
        last_action = action.astype(np.float32)

        if recording and frames >= max_frames:
            dataset.save_episode()
            return "saved"

        status = "RECORDING" if recording else "ready - space to start"
        viewer.show(
            frame,
            [
                f"episode {saved + 1}/{total}   {status}",
                f"frames {frames}   throttle {action[0]:+0.2f}  steer {action[1]:+0.2f}",
            ],
        )

        elapsed = time.monotonic() - started
        if elapsed < period:
            time.sleep(period - elapsed)
