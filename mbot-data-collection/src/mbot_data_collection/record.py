"""Record teleoperated episodes into a LeRobotDataset.

`lerobot-record` drives robots through its own teleoperation stack and does not
know this chassis, so the loop is hand-rolled. The one step that must not be
skipped is `finalize()`: the CLI calls it for you, and a hand-rolled loop that
forgets it leaves a dataset that looks written but will not load.

What lands in each frame, per control tick:

    observation.images.webcam   the frame as it looked before you acted
    observation.state           the action commanded on the previous tick
    action                      the action commanded now

`observation.state` is the previous action rather than a measured pose because
this mBot has no encoders and no way to know where it is. That keeps the feature
shapes identical to the simulated sibling app, so a policy pre-trained there can
be fine-tuned on this data without renaming anything but the camera key.

The action is the stick, not the wheels: what a policy learns to predict is
forward speed and turn rate, and the chassis mapping - steer gain, differential
mixing, the duty floor and ceiling - is applied afterwards, identically at
record time and at deploy time. The price of that choice is that an action only
means a particular motion *given a particular chassis configuration*, so the
configuration is written beside the episodes rather than left in a file that
someone will later tune. A policy replayed under a different steer gain would
quietly drive differently from the demonstrations it learned from.
"""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .config import CONTROL_HZ, RobotConfig
from .link import MBotLink

# A hand-driven episode that runs this long is a failed one; stop it rather than
# filling the dataset with a minute of aimless driving.
MAX_EPISODE_SECONDS = 60.0


@dataclass
class RecordConfig:
    repo_id: str
    root: Path
    task: str
    episodes: int = 5
    window: int = 720
    push_to_hub: bool = False
    private: bool = False
    resume: bool = False
    prefer_keyboard: bool = False


def _features(height: int, width: int) -> dict:
    return {
        "observation.images.webcam": {
            "dtype": "video",
            "shape": (height, width, 3),
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


def record(config: RecordConfig, robot: RobotConfig) -> int:
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    from .camera import Camera
    from .ui import Teleop, Viewer

    camera = Camera(robot.camera_index, robot.camera_width, robot.camera_height, robot.camera_name, robot.camera_map)
    camera.open()
    height, width = camera.shape[:2]

    existing = 0
    if config.resume:
        if not config.root.exists():
            print(f"Nothing to resume at {config.root}.")
            camera.close()
            return 1
        dataset = LeRobotDataset.resume(config.repo_id, root=str(config.root))
        existing = dataset.num_episodes
        print(f"Resuming {config.root} with {existing} episode(s) already recorded.")
    elif config.root.exists():
        print(f"{config.root} already exists.\n  Add to it with --resume, or pick another --root.")
        camera.close()
        return 1
    else:
        dataset = LeRobotDataset.create(
            repo_id=config.repo_id,
            fps=int(robot.control_hz),
            features=_features(height, width),
            root=str(config.root),
            robot_type="mbot",
        )

    # The mapping from action to wheels, saved beside the episodes. Without it
    # a recorded action is uninterpretable later: the same numbers mean a
    # different motion under a different steer gain or duty ceiling.
    _write_chassis(config.root, robot)

    viewer = Viewer(width=config.window, title="mbot - record")
    teleop = Teleop(
        throttle_axis=robot.throttle_axis,
        steer_axis=robot.steer_axis,
        prefer_keyboard=config.prefer_keyboard,
        deadzone=robot.stick_deadzone,
    )
    period = 1.0 / robot.control_hz
    max_frames = int(MAX_EPISODE_SECONDS * robot.control_hz)

    print(f"Recording {config.episodes} episode(s) with {teleop.source}.")
    print(f"  task: {config.task}")
    print("  space  start / stop an episode")
    print("  r      discard the episode in progress and start it over")
    print("  q      quit")

    saved = 0
    try:
        with MBotLink(robot.port, watchdog_ms=robot.watchdog_ms, baud=robot.baud) as link:
            print(f"  board: {link.banner}")
            while saved < config.episodes:
                outcome = _record_one(
                    link, robot, camera, dataset, viewer, teleop,
                    config, period, max_frames, saved,
                )
                if outcome == "quit":
                    break
                if outcome == "saved":
                    saved += 1
                    link.beep(1320, 80)
                    print(f"  episode {saved}/{config.episodes} saved")
    except KeyboardInterrupt:
        pass
    finally:
        teleop.close()
        viewer.close()
        camera.close()

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


def _write_chassis(root: Path, robot: RobotConfig) -> None:
    """Record the action -> wheels mapping this dataset was collected under."""
    from dataclasses import asdict

    path = root / "chassis.json"
    current = {
        key: value
        for key, value in asdict(robot).items()
        # Which port and camera were used is provenance, not interpretation;
        # what matters for replaying an action is the mapping to the wheels.
        if key in {
            "control_hz", "min_pwm", "max_pwm", "steer_gain",
            "stick_deadzone", "swap_motors", "invert_left", "invert_right",
        }
    }

    if path.exists():
        previous = json.loads(path.read_text())
        drifted = {k: (previous.get(k), v) for k, v in current.items() if previous.get(k) != v}
        if drifted:
            print("warning: the chassis configuration has changed since this")
            print("         dataset was started. Episodes recorded now will not")
            print("         mean the same motion as the earlier ones:")
            for key, (was, now) in drifted.items():
                print(f"           {key}: {was} -> {now}")
        return

    root.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, indent=2) + "\n")


def _record_one(
    link: MBotLink,
    robot: RobotConfig,
    camera,
    dataset,
    viewer,
    teleop,
    config: RecordConfig,
    period: float,
    max_frames: int,
    saved: int,
) -> str:
    """Run one episode. Returns 'saved', 'discarded', or 'quit'."""
    import pygame

    recording = False
    frames = 0
    last_action = np.zeros(2, dtype=np.float32)

    def park() -> None:
        link.drive_pwm(0, 0)
        teleop.reset()

    while True:
        started = time.monotonic()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                park()
                return "quit"
            if event.type != pygame.KEYDOWN:
                continue
            if event.key == pygame.K_q:
                park()
                return "quit"
            if event.key == pygame.K_r:
                # Drop whatever was buffered; the episode never happened.
                dataset.clear_episode_buffer()
                park()
                return "discarded"
            if event.key == pygame.K_SPACE:
                if not recording:
                    recording = True
                else:
                    park()
                    if frames == 0:
                        return "discarded"
                    dataset.save_episode()
                    return "saved"

        frame = camera.latest()
        action = teleop.read(period)

        # The observation is written before acting on it, so a frame is always
        # paired with the action taken in response to it, never after.
        if recording and frame is not None:
            dataset.add_frame(
                {
                    "observation.images.webcam": frame,
                    "observation.state": last_action,
                    "action": action.astype(np.float32),
                    "task": config.task,
                }
            )
            frames += 1

        left, right = robot.wheels(action)
        link.stream_pwm(*robot.to_pwm(left, right))
        last_action = action.astype(np.float32)

        if recording and frames >= max_frames:
            park()
            dataset.save_episode()
            return "saved"

        status = "RECORDING" if recording else "ready - space to start"
        viewer.show(
            frame if frame is not None else np.zeros((robot.camera_height, robot.camera_width, 3), np.uint8),
            [
                f"episode {saved + 1}/{config.episodes}   {status}",
                f"frames {frames}   throttle {action[0]:+0.2f}  steer {action[1]:+0.2f}",
                config.task,
            ],
        )

        elapsed = time.monotonic() - started
        if elapsed < period:
            time.sleep(period - elapsed)


def push(repo_id: str, root: Path, private: bool = False) -> int:
    """Upload an already-recorded local dataset to the Hub."""
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    if not root.exists():
        print(f"No dataset at {root}.")
        return 1

    dataset = LeRobotDataset(repo_id, root=str(root))
    print(f"Pushing {dataset.num_episodes} episode(s) to {repo_id} ...")
    dataset.push_to_hub(private=private, tags=["lerobot", "mbot", "teleoperation"])
    print(f"  https://huggingface.co/datasets/{repo_id}")
    return 0
