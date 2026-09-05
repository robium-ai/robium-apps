"""Record teleoperated episodes into a LeRobotDataset.

`lerobot-record` drives robots through its own teleoperation stack and does not
know this chassis, so the loop is hand-rolled. The one step that must not be
skipped is `finalize()`: the CLI calls it for you, and a hand-rolled loop that
forgets it leaves a dataset that looks written but will not load.

What lands in each frame, per control tick:

    observation.images.webcam   the frame as it looked before you acted
    observation.state           the action commanded on the previous tick
    action                      the action commanded now
    task                        the instruction this episode demonstrates

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

A session can carry more than one instruction. A vision-language-action policy
only learns that the words matter if the same scene appears under different
words with different demonstrations, so "push the blue block to the blue zone"
and "push the blue block to the red zone" belong in *one* dataset rather than
two.

Which instruction an episode demonstrates is chosen by the operator and by
nobody else. The obvious convenience - pre-selecting whichever instruction has
fewer episodes, so that simply pressing space alternates - is a trap: it decides
what you are about to drive before you drive it, and every time that guess is
wrong the episode is saved under the other goal. Keeping the pair balanced is
worth something, but not that; the counts are shown beside each instruction so
an imbalance stays visible, and correcting it is a matter of pressing the other
number.
"""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .config import CONTROL_HZ, RobotConfig
from .link import MBotLink

# A hand-driven episode that runs this long is a failed one; stop it rather than
# filling the dataset with a minute of aimless driving.
MAX_EPISODE_SECONDS = 60.0

# An episode this short is a double-tapped space bar, not a demonstration.
# Saving it costs an episode slot and puts a frame or two of meaningless action
# into the training set; `frames == 0` alone does not catch it.
MIN_EPISODE_FRAMES = 10

DEFAULT_TASK = "drive the robot to the goal"

# Number keys 1..9 pick an instruction; more than that would not fit on screen
# and is not a session anyone drives by hand.
MAX_TASKS = 9


@dataclass
class RecordConfig:
    repo_id: str
    root: Path
    # Empty means "whatever this dataset was already being recorded under",
    # resolved in record() from tasks.json or the dataset's own metadata.
    tasks: list[str] = field(default_factory=list)
    episodes: int = 5
    window: int = 720
    push_to_hub: bool = False
    private: bool = False
    resume: bool = False
    prefer_keyboard: bool = False


@dataclass
class _Session:
    """What the operator has chosen and collected so far, across episodes."""

    tasks: list[str]
    counts: dict[str, int]
    # Changed only by the operator pressing a number key, and it stays put
    # across episodes. Nothing here ever picks an instruction on its own: an
    # instruction the app chooses is a guess about what the human is about to
    # drive, and a wrong guess writes a wrong label. An imbalance is visible in
    # the counts and can be corrected later; a mislabeled episode is
    # indistinguishable from noise at training time.
    selected: int = 0

    @property
    def task(self) -> str:
        return self.tasks[self.selected]


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

    tasks = _resolve_tasks(config, dataset)
    if not tasks:
        print("No instruction to record under; pass --task.")
        camera.close()
        return 1

    # The mapping from action to wheels, saved beside the episodes. Without it
    # a recorded action is uninterpretable later: the same numbers mean a
    # different motion under a different steer gain or duty ceiling.
    _write_chassis(config.root, robot)
    _write_tasks(config.root, tasks)

    session = _Session(tasks=tasks, counts=_task_counts(dataset, tasks))

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
    for index, task in enumerate(tasks, start=1):
        already = session.counts.get(task, 0)
        print(f"  {index}  {task}" + (f"   ({already} already)" if already else ""))
    print("  space  start / stop an episode")
    if len(tasks) > 1:
        print(f"  1-{len(tasks)}    choose which instruction the next episode demonstrates")
    print("  r      discard the episode in progress and start it over")
    print("  q      quit")

    saved = 0
    try:
        with MBotLink(robot.port, watchdog_ms=robot.watchdog_ms, baud=robot.baud) as link:
            print(f"  board: {link.banner}")
            while saved < config.episodes:
                outcome, task = _record_one(
                    link, robot, camera, dataset, viewer, teleop, session,
                    config, period, max_frames, saved,
                )
                if outcome == "quit":
                    break
                if outcome == "discarded":
                    link.beep(440, 120)
                if outcome == "saved":
                    saved += 1
                    session.counts[task] = session.counts.get(task, 0) + 1
                    link.beep(1320, 80)
                    print(f"  episode {saved}/{config.episodes} saved   [{task}]")
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
    for task in tasks:
        print(f"  {session.counts.get(task, 0):>4}  {task}")
    if saved < config.episodes:
        print(f"  ({saved} of {config.episodes} recorded this session)")
        print(f"  Add more later:  ./app record --repo-id {config.repo_id} --resume")

    if config.push_to_hub:
        return push(config.repo_id, config.root, private=config.private)
    print(f"  Upload later:    ./app push --repo-id {config.repo_id}")
    return 0


def _resolve_tasks(config: RecordConfig, dataset) -> list[str]:
    """The instructions this session records under.

    Given on the command line, else remembered from the dataset being resumed,
    so a fifty-episode collection spread over several sittings does not depend
    on retyping two sentences identically - a typo would silently become a
    third instruction with a handful of episodes under it.
    """
    if config.tasks:
        return list(dict.fromkeys(config.tasks))[:MAX_TASKS]

    remembered = _read_tasks(config.root)
    if remembered:
        return remembered[:MAX_TASKS]

    known = list(getattr(dataset.meta, "tasks", {}).index) if config.resume else []
    return known[:MAX_TASKS] if known else [DEFAULT_TASK]


def _task_counts(dataset, tasks: list[str]) -> dict[str, int]:
    """How many episodes each instruction already has, to keep the pair level."""
    counts = {task: 0 for task in tasks}
    episodes = getattr(dataset.meta, "episodes", None)
    if episodes is None or "tasks" not in getattr(episodes, "column_names", []):
        return counts
    for recorded in episodes["tasks"]:
        for task in recorded if isinstance(recorded, (list, tuple)) else [recorded]:
            counts[task] = counts.get(task, 0) + 1
    return counts


def _write_tasks(root: Path, tasks: list[str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "tasks.json").write_text(json.dumps(tasks, indent=2) + "\n")


def _read_tasks(root: Path) -> list[str]:
    path = root / "tasks.json"
    if not path.exists():
        return []
    return [str(task) for task in json.loads(path.read_text())]


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


def _overlay(session: _Session, saved: int, config: RecordConfig, action, frames: int, recording: bool) -> list[str]:
    status = "RECORDING" if recording else "ready - space to start"
    lines = [
        f"episode {saved + 1}/{config.episodes}   {status}",
        f"frames {frames}   throttle {action[0]:+0.2f}  steer {action[1]:+0.2f}",
    ]
    if recording or len(session.tasks) == 1:
        lines.append(session.task)
        return lines
    # Between episodes the chooser is the useful thing to show, with each
    # instruction's episode count beside it so an imbalance is visible while
    # there is still time to correct it.
    for index, task in enumerate(session.tasks):
        marker = ">" if index == session.selected else " "
        lines.append(f"{marker} {index + 1}  {task}   ({session.counts.get(task, 0)})")
    return lines


def _record_one(
    link: MBotLink,
    robot: RobotConfig,
    camera,
    dataset,
    viewer,
    teleop,
    session: _Session,
    config: RecordConfig,
    period: float,
    max_frames: int,
    saved: int,
) -> tuple[str, str]:
    """Run one episode. Returns (outcome, task), outcome in saved/discarded/quit."""
    import pygame

    recording = False
    frames = 0
    last_action = np.zeros(2, dtype=np.float32)
    # Fixed when recording starts: an instruction switched mid-episode would
    # label frames the operator drove under the other one.
    task = session.task

    def park() -> None:
        link.drive_pwm(0, 0)
        teleop.reset()

    print(f"  next: {session.task}")

    while True:
        started = time.monotonic()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                park()
                return "quit", task
            if event.type != pygame.KEYDOWN:
                continue
            if event.key == pygame.K_q:
                park()
                return "quit", task
            if event.key == pygame.K_r:
                # Drop whatever was buffered; the episode never happened.
                dataset.clear_episode_buffer()
                park()
                return "discarded", task
            if not recording and pygame.K_1 <= event.key <= pygame.K_9:
                choice = event.key - pygame.K_1
                if choice < len(session.tasks) and choice != session.selected:
                    session.selected = choice
                    print(f"  next: {session.task}")
                continue
            if event.key == pygame.K_SPACE:
                if not recording:
                    recording = True
                    task = session.task
                    link.beep(880, 60)
                else:
                    park()
                    if frames < MIN_EPISODE_FRAMES:
                        if frames:
                            print(f"  too short ({frames} frames); discarded")
                        dataset.clear_episode_buffer()
                        return "discarded", task
                    dataset.save_episode()
                    return "saved", task

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
                    "task": task,
                }
            )
            frames += 1

        left, right = robot.wheels(action)
        link.stream_pwm(*robot.to_pwm(left, right))
        last_action = action.astype(np.float32)

        if recording and frames >= max_frames:
            park()
            dataset.save_episode()
            return "saved", task

        viewer.show(
            frame if frame is not None else np.zeros((robot.camera_height, robot.camera_width, 3), np.uint8),
            _overlay(session, saved, config, action, frames, recording),
        )

        elapsed = time.monotonic() - started
        if elapsed < period:
            time.sleep(period - elapsed)


# The arena as it sits in a 640x480 frame from the fixed overhead camera, in
# TL, TR, BR, BL order. Read off a recorded frame rather than detected: the
# board, the floor and the painted zones do not separate on brightness (Otsu
# takes the whole room) or on saturation (20.6 vs 28.5), and a detector keyed on
# "white" eats the blue and red zones themselves. For a camera that does not
# move, four hand-checked numbers are simpler and correct.
ARENA_QUAD = ((146, 56), (489, 53), (475, 410), (136, 407))

# The rectified arena is square because the board is. Matching the policy's own
# 512x512 input means the frame is resampled once, here, instead of twice.
ARENA_SIZE = 512


def arena_matrix(quad, size: int = ARENA_SIZE):
    """The perspective transform taking the arena corners to a square."""
    import cv2

    source = np.asarray(quad, dtype=np.float32)
    target = np.float32([[0, 0], [size - 1, 0], [size - 1, size - 1], [0, size - 1]])
    return cv2.getPerspectiveTransform(source, target)


def crop_arena(
    repo_id: str, root: Path, out_repo_id: str, out_root: Path,
    quad: tuple[tuple[int, int], ...] = ARENA_QUAD,
    size: int = ARENA_SIZE,
) -> int:
    """Copy a dataset rectified to the arena: the board warped to a square.

    Two things are wrong with the raw frame. Everything outside the board - the
    floor, the stairs, cables, whatever was left lying around - is nuisance that
    carries nothing about the task and is exactly what differs between the
    session the data was collected in and the evening it is replayed in. And the
    arena covers only 41% of the frame, so more than half of every image is
    background and the block, the smallest thing that matters, lands on about
    40x22 pixels once squeezed into the model's 512x512 input.

    A perspective warp fixes both at once and does something a crop cannot: the
    camera looks at the board slightly off-square, so the board is a
    quadrilateral and a given physical position lands on different pixels
    depending on where it is in the frame. Rectifying makes the mapping from the
    floor to the image uniform, which is the geometry a fixed overhead camera
    was supposed to provide in the first place.

    The corners are written to `arena.json` beside the episodes so `./app
    rollout` applies the identical warp to live frames. That is not bookkeeping:
    a policy trained on rectified frames and fed raw ones, or the reverse, is
    being shown something it has never seen, and fails in a way that looks like
    a bad policy rather than a mismatched pipeline.
    """
    import cv2
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    if out_root.exists():
        print(f"{out_root} already exists; remove it or choose another --out-root.")
        return 1

    source = LeRobotDataset(repo_id, root=str(root))
    height, width = source.meta.features["observation.images.webcam"]["shape"][:2]
    matrix = arena_matrix(quad, size)
    print(f"Rectifying {source.num_episodes} episode(s), {source.num_frames} frames: "
          f"{width}x{height} -> {size}x{size}")

    target = LeRobotDataset.create(
        repo_id=out_repo_id,
        fps=int(source.fps),
        features=_features(size, size),
        root=str(out_root),
        robot_type=source.meta.robot_type,
    )

    lengths = list(source.meta.episodes["length"])
    index = 0
    for episode, length in enumerate(lengths):
        for _ in range(length):
            frame = source[index]
            image = (frame["observation.images.webcam"].numpy().transpose(1, 2, 0) * 255)
            target.add_frame({
                "observation.images.webcam": cv2.warpPerspective(
                    image.astype(np.uint8), matrix, (size, size), flags=cv2.INTER_LINEAR),
                "observation.state": frame["observation.state"].numpy().astype(np.float32),
                "action": frame["action"].numpy().astype(np.float32),
                "task": frame["task"],
            })
            index += 1
        target.save_episode()
        print(f"  episode {episode + 1}/{len(lengths)}", end="\r", flush=True)
    target.finalize()

    (out_root / "arena.json").write_text(json.dumps({
        "quad": [[int(x), int(y)] for x, y in quad],
        "size": size,
        "source_shape": [height, width],
    }, indent=2) + "\n")
    for name in ("chassis.json", "tasks.json"):
        if (root / name).exists():
            (out_root / name).write_text((root / name).read_text())

    print(f"\nWrote {target.num_episodes} episode(s) to {out_root}")
    print(f"  Upload with:  ./app push --repo-id {out_repo_id} --private")
    return 0


def drop_state(
    repo_id: str, root: Path, out_repo_id: str, out_root: Path,
) -> int:
    """Copy a dataset with `observation.state` blanked to zeros.

    Measured on the first policy trained from this app: it had learned to copy
    its own previous action rather than to look at the camera. Varying the image
    while holding the state fixed moved its predictions by 0.149; varying the
    state while holding the image fixed moved them by 0.279 (throttle) and 0.580
    (steer), and its output sat 0.031 away from the previous action it was
    handed. Training loss was 0.033 and the robot never approached the block.

    That is the copycat shortcut, and `observation.state = the previous action`
    is what offers it: at 20 Hz two consecutive teleop commands are nearly
    identical, so `action_t ~= state_t` predicts the training set almost
    perfectly without the policy ever having to see anything. A chassis with no
    encoders is the worst case for it, because the last command is the only
    proprioception there is - so the honest choice is to record no proprioception
    at all.

    The feature is zeroed rather than removed because SmolVLA requires it:
    `prepare_state` indexes `batch["observation.state"]` with no fallback, so a
    dataset without the key raises KeyError on the first forward pass. A constant
    feature carries no information, which is the point, and normalization is safe
    on one because the normalizer divides by `std + eps`.
    """
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    if out_root.exists():
        print(f"{out_root} already exists; remove it or choose another --out-root.")
        return 1

    source = LeRobotDataset(repo_id, root=str(root))
    height, width = source.meta.features["observation.images.webcam"]["shape"][:2]
    lengths = list(source.meta.episodes["length"])
    dropped = [i for i, n in enumerate(lengths) if n < MIN_EPISODE_FRAMES]
    if dropped:
        print(f"Skipping {len(dropped)} episode(s) shorter than {MIN_EPISODE_FRAMES} frames: {dropped}")
    print(f"Rewriting {source.num_episodes - len(dropped)} episode(s) "
          f"with observation.state zeroed.")

    target = LeRobotDataset.create(
        repo_id=out_repo_id,
        fps=int(source.fps),
        features=_features(height, width),
        root=str(out_root),
        robot_type=source.meta.robot_type,
    )

    zero = np.zeros(2, dtype=np.float32)
    index = 0
    for episode, length in enumerate(lengths):
        if length < MIN_EPISODE_FRAMES:
            index += length
            continue
        for _ in range(length):
            frame = source[index]
            image = (frame["observation.images.webcam"].numpy().transpose(1, 2, 0) * 255)
            target.add_frame({
                "observation.images.webcam": image.astype(np.uint8),
                "observation.state": zero,
                "action": frame["action"].numpy().astype(np.float32),
                "task": frame["task"],
            })
            index += 1
        target.save_episode()
        print(f"  episode {episode + 1}/{len(lengths)}", end="\r", flush=True)
    target.finalize()

    # Provenance travels with the copy: the chassis the episodes were driven
    # under, and the instructions they were driven for, are as true of the
    # rewrite as of the original.
    for name in ("chassis.json", "tasks.json"):
        if (root / name).exists():
            (out_root / name).write_text((root / name).read_text())

    print(f"\nWrote {target.num_episodes} episode(s) to {out_root}")
    print(f"  Upload with:  ./app push --repo-id {out_repo_id} --private")
    return 0


# Below this on both axes the robot is not being asked to move. Teleop pauses
# sit here: the operator stops to look, and the recording keeps writing frames
# whose correct action is "do nothing".
IDLE_ACTION = 0.02

# An idle run this long is a pause rather than a momentary lull, and worth
# cutting at. Five frames is a quarter second at 20 Hz.
IDLE_GAP_FRAMES = 5

# Idle frames kept at the end of a segment, so arriving and stopping is still
# demonstrated rather than trained out.
KEEP_TRAILING_IDLE = 4


def _motion_segments(actions: np.ndarray) -> list[tuple[int, int]]:
    """Runs of frames to keep, as [start, end) into one episode's actions.

    Cuts the episode at pauses instead of deleting the pause frames in place.
    Deleting them would leave the survivors adjacent in index but seconds apart
    in reality, and an action chunk is a window over consecutive indices - so a
    filtered-in-place episode teaches trajectories that jump through time. A cut
    keeps every remaining chunk describing real, contiguous motion.
    """
    idle = (np.abs(actions[:, 0]) < IDLE_ACTION) & (np.abs(actions[:, 1]) < IDLE_ACTION)
    segments: list[tuple[int, int]] = []
    start = None
    run = 0
    for i, is_idle in enumerate(idle):
        if is_idle:
            run += 1
            # A brief lull mid-manoeuvre is part of the motion; only a sustained
            # pause ends a segment.
            if run == IDLE_GAP_FRAMES and start is not None:
                segments.append((start, i - IDLE_GAP_FRAMES + 1 + KEEP_TRAILING_IDLE))
                start = None
        else:
            run = 0
            if start is None:
                start = i
    if start is not None:
        segments.append((start, len(idle)))
    return [(a, min(b, len(idle))) for a, b in segments
            if min(b, len(idle)) - a >= MIN_EPISODE_FRAMES]


def split_motion(
    repo_id: str, root: Path, out_repo_id: str, out_root: Path, seed: int = 0,
) -> int:
    """Copy a dataset cut at teleop pauses, with the episode order shuffled.

    Two defects are fixed at once, both measured rather than assumed.

    Nearly half the frames recorded here carry no command at all - 46% of the
    pushing dataset and 58% of the driving one had zero throttle. Those are the
    operator's own pauses, and they teach the policy that the most likely action
    in any frame is to stop, which is what a rolled-out policy then does. Worse,
    a paused frame and a frame driven through at speed can be pixel-identical,
    so the target is not a function of the observation and no model can fit it.

    The shuffle is for the split, not the training: `--dataset.eval_split` holds
    out the *last* ceil(n * 0.2) episodes, so on a dataset written in recording
    order the held-out set is the end of the session - and any drift in lighting
    or in the operator's driving over that session lands entirely in it.
    Permuting here makes those last episodes a random sample instead.
    """
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    if out_root.exists():
        print(f"{out_root} already exists; remove it or choose another --out-root.")
        return 1

    source = LeRobotDataset(repo_id, root=str(root))
    height, width = source.meta.features["observation.images.webcam"]["shape"][:2]
    lengths = list(source.meta.episodes["length"])

    # Gather every segment first: the shuffle needs them all in hand, and the
    # frames are read by absolute index anyway.
    offset = 0
    plan: list[tuple[int, int]] = []
    for length in lengths:
        actions = np.stack([source[offset + i]["action"].numpy() for i in range(length)])
        for start, end in _motion_segments(actions):
            plan.append((offset + start, offset + end))
        offset += length

    kept = sum(end - start for start, end in plan)
    print(f"{len(lengths)} episode(s), {offset} frames -> "
          f"{len(plan)} segment(s), {kept} frames "
          f"({100 * (1 - kept / max(offset, 1)):.0f}% of frames were pauses)")

    rng = np.random.default_rng(seed)
    rng.shuffle(plan)

    target = LeRobotDataset.create(
        repo_id=out_repo_id,
        fps=int(source.fps),
        features=_features(height, width),
        root=str(out_root),
        robot_type=source.meta.robot_type,
    )
    zero = np.zeros(2, dtype=np.float32)
    for number, (start, end) in enumerate(plan, start=1):
        for index in range(start, end):
            frame = source[index]
            image = (frame["observation.images.webcam"].numpy().transpose(1, 2, 0) * 255)
            target.add_frame({
                "observation.images.webcam": image.astype(np.uint8),
                "observation.state": zero,
                "action": frame["action"].numpy().astype(np.float32),
                "task": frame["task"],
            })
        target.save_episode()
        print(f"  segment {number}/{len(plan)}", end="\r", flush=True)
    target.finalize()

    for name in ("chassis.json", "tasks.json"):
        if (root / name).exists():
            (out_root / name).write_text((root / name).read_text())

    print(f"\nWrote {target.num_episodes} episode(s) to {out_root}")
    print(f"  Upload with:  ./app push --repo-id {out_repo_id} --private")
    return 0


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
