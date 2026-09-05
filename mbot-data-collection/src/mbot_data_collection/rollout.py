"""Drive the real mBot from a trained policy.

The same control tick as `drive`, with the policy holding the sticks: read a
frame, ask for an action, mix it to wheels, apply the chassis wiring, send one
command. That symmetry is the point of recording the stick rather than the
wheels - the mapping from action to duty is identical here and at record time,
so a policy reproduces the motion it was shown instead of a rescaled version of
it.

Three things about this differ from the simulated sibling, and each one is a
way a rollout can look broken when it is not:

**The instruction is live.** Switching it is the whole reason both goals were
recorded, so number keys change it mid-run. But SmolVLA emits a *chunk* of
actions per forward pass and serves them from a queue, so a new instruction
would otherwise sit unused until the queue drained - seconds of the robot
visibly ignoring the words. Switching therefore calls `policy.reset()`, which
drops the queue and forces a forward pass against the new instruction.

**The wire is fed by its own thread.** A forward pass takes far longer than the
50 ms control period, and the board stops the wheels if it hears nothing for
`watchdog_ms`. Left in one loop, every refill of the chunk queue would trip the
watchdog and the robot would stutter. The feeder streams the current command at
a steady rate whichever way the main loop is spending its time, and dies with
the process - so a crashed host still silences the wire and still stops the
robot.

**The policy runs in a second thread, and chunks overlap.** Feeding the wire
steadily is not enough on its own. Measured here, one forward pass costs ~430 ms
- nine control ticks - and a synchronous loop computes it *before* updating the
command, so the previous action stays on the wire for ~480 ms instead of 50 ms.
That is one action held nine times too long every 2.5 s, and it drags the
effective rate to 17.4 Hz against the 20 Hz the demonstrations were recorded at.
Shortening the chunk does not fix it; it makes the stall more frequent.

So the policy runs in a worker thread while the control loop keeps consuming the
chunk already in hand, and the two are stitched together with Real-Time Chunking
(`RTCConfig`), which conditions each new chunk on the actions that will execute
while it is being computed. `inference_delay` tells RTC how many of those are
already committed - measured from the previous pass rather than assumed - so the
seam between chunks is continuous instead of a jump. With the stall gone,
`RTC_EXECUTION_HORIZON` sets how often the policy re-plans, and it can be short
without costing anything: ten ticks means it looks at a fresh frame twice a
second rather than once every two and a half.

**Nothing here scores the run.** The simulator knew where the block was; a
webcam does not. What a rollout is for is watching whether the same scene under
two different instructions produces two different behaviours.
"""

from __future__ import annotations

import inspect
import json
import math
import threading
import time
from dataclasses import dataclass, field, fields
from pathlib import Path

import numpy as np

from .config import RobotConfig
from .link import MBotLink

# SmolVLA inherits smolvla_base's three-camera config verbatim - fine-tuning
# never rewrites it - so inference has to apply the same mapping training did.
# ACT has no such constraint and trains on the dataset's own key, so its map is
# empty. Guessing either way silently feeds the policy a camera it never saw, so
# the map is read from the checkpoint rather than assumed.
FALLBACK_RENAME_MAP = {"observation.images.webcam": "observation.images.camera1"}


def _trained_rename_map(path: str) -> dict[str, str]:
    """The rename map the checkpoint was trained with.

    `train_config.json` records it, so a checkpoint carries its own answer and
    ACT and SmolVLA can share one rollout path. Older checkpoints predate the
    field; those are SmolVLA, and fall back to its mapping.
    """
    config_path = Path(path) / "train_config.json"
    if not config_path.is_file():
        return dict(FALLBACK_RENAME_MAP)
    saved = json.loads(config_path.read_text()).get("rename_map")
    return dict(saved) if saved is not None else dict(FALLBACK_RENAME_MAP)

# A rollout that has run this long is not going to start working; stop it rather
# than letting a confused policy drive into a wall until someone notices.
MAX_RUN_SECONDS = 120.0

# How many actions of a chunk to execute before the next chunk should be ready.
# This is the re-planning period, not a latency budget: the worker thread is
# already computing the next chunk while these run, so shortening it buys
# reactivity rather than costing stalls. Ten ticks is half a second at 20 Hz.
RTC_EXECUTION_HORIZON = 10


@dataclass
class RolloutConfig:
    policy_path: str
    dataset_repo_id: str
    dataset_root: Path | None = None
    tasks: list[str] = field(default_factory=list)
    window: int = 720
    device: str = "mps"
    rename_map: dict[str, str] | None = None
    # Drive from a recorded episode's frames instead of the camera. The robot
    # still moves; only the eyes are replaced.
    replay_episode: int | None = None
    # RTC stitches a new chunk onto the actions already committed, which is what
    # lets a 262ms forward pass drive a 20Hz robot. It is also an inference-time
    # change the checkpoint never trained under, so turning it off is how we
    # tell a policy that cannot do the task from one our execution is distorting.
    use_rtc: bool = True
    # Flow matching denoises from fresh noise every call, so the same frame can
    # yield very different chunks - measured at 0.435 std on one frame, against
    # 0.311 for the whole dataset's actions. Drawing several and taking the
    # median spends one batched pass to stop a single unlucky draw from
    # committing the robot to half a second of it. ACT is deterministic and
    # ignores this.
    samples: int = 1
    # Drive a chunk, halt, let the robot actually come to rest, and only then
    # look and plan again. It gives up smooth motion to buy the one thing the
    # simulator has for free: a frame that is still true when the chunk built
    # from it starts executing. Latency stops mattering, because nothing moves
    # while the policy thinks.
    stop_and_go: bool = False
    # How long to hold the wheels at zero before looking. Long enough that the
    # robot has stopped coasting, or the frame is a motion blur of where it was.
    settle_seconds: float = 0.5
    # Actions committed per chunk. Longer chunks give a slow policy more wall
    # clock to think between plans, at the cost of acting on a staler frame.
    execution_horizon: int = RTC_EXECUTION_HORIZON


def _local_checkpoint(policy_path: str) -> str:
    """A local directory for the checkpoint, downloading it if needed.

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
        # Per-step checkpoints and their optimizer state are gigabytes and
        # irrelevant to inference.
        ignore_patterns=["checkpoints/*"],
    )


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

    # Set before the policy is constructed: __init__ builds the RTC processor
    # and hands it to the flow-matching model, so enabling it afterwards would
    # leave the model without one. Only flow-matching policies declare the
    # field; ACT has no RTC path, and bolting the attribute onto its config
    # would promise a capability its forward pass does not have.
    if config.use_rtc and "rtc_config" in {f.name for f in fields(cfg)} and cfg.rtc_config is None:
        from lerobot.policies.rtc.configuration_rtc import RTCConfig

        cfg.rtc_config = RTCConfig(enabled=True, execution_horizon=config.execution_horizon)

    meta = LeRobotDatasetMetadata(
        config.dataset_repo_id,
        root=str(config.dataset_root) if config.dataset_root else None,
    )
    rename_map = config.rename_map if config.rename_map is not None else _trained_rename_map(path)
    policy = make_policy(cfg, ds_meta=meta, rename_map=rename_map)

    # The saved preprocessor names its tokenizer by the relative path
    # "tokenizer", resolved against the working directory rather than the
    # checkpoint. Point it at the copy that ships inside the checkpoint.
    overrides: dict[str, dict] = {}
    tokenizer_dir = Path(path) / "tokenizer"
    if tokenizer_dir.is_dir():
        overrides["tokenizer_processor"] = {"tokenizer_name": str(tokenizer_dir)}
    # The processor also bakes in the device it was trained on - "cuda" for a
    # run on HF Jobs - which is not what we are driving from.
    overrides["device_processor"] = {"device": config.device}
    preprocessor, postprocessor = make_pre_post_processors(
        cfg, pretrained_path=path, preprocessor_overrides=overrides
    )
    policy.eval()
    return policy, preprocessor, postprocessor


def arena_transform(root: Path | None):
    """The arena rectification the policy's training data was built with, or None.

    Read from `arena.json` beside the episodes rather than configured here, so
    live frames go through exactly what the training frames went through.
    Getting this wrong in either direction - a rectified policy fed raw frames,
    or a raw-frame policy fed rectified ones - produces a robot that looks like
    it never learned anything.
    """
    if root is None:
        return None
    path = root / "arena.json"
    if not path.exists():
        return None

    import cv2

    from .record import arena_matrix

    spec = json.loads(path.read_text())
    size = int(spec["size"])
    height, width = spec["source_shape"]
    matrix = arena_matrix(spec["quad"], size)

    def rectify(frame: np.ndarray) -> np.ndarray:
        if frame.shape[:2] != (height, width):
            raise ValueError(
                f"camera gives {frame.shape[:2]}, but this policy's arena was "
                f"measured on {(height, width)}; recalibrate or use the right camera"
            )
        return cv2.warpPerspective(frame, matrix, (size, size), flags=cv2.INTER_LINEAR)

    rectify.shape = (size, size)
    return rectify


def training_brightness(repo_id: str, root: Path | None) -> np.ndarray | None:
    """Mean per-channel brightness of the frames the policy was trained on.

    A policy trained on a few minutes of video under one lighting condition has
    no reason to be robust to a different one, and the difference is invisible
    to the eye once you have been staring at the arena all evening. The dataset
    already carries the number, so the rollout can show how far the room has
    drifted while there is still a chance to fix it with a lamp.
    """
    from lerobot.datasets.lerobot_dataset import LeRobotDatasetMetadata

    meta = LeRobotDatasetMetadata(repo_id, root=str(root) if root else None)
    stats = meta.stats.get("observation.images.webcam")
    if not stats or "mean" not in stats:
        return None
    return np.ravel(np.asarray(stats["mean"], dtype=float)) * 255.0


def state_is_constant(repo_id: str, root: Path | None) -> bool:
    """Was this policy trained on a dataset whose observation.state never moved?

    `./app drop-state` zeroes the feature to deny the policy the copycat
    shortcut, and a policy trained that way has never once seen a nonzero state.
    Feeding it the previous action at rollout - which is what the feature means
    on a dataset recorded normally - would hand it an input off the edge of
    anything in its training distribution. The training dataset's own statistics
    say which kind it is, so neither the operator nor a flag has to remember.
    """
    from lerobot.datasets.lerobot_dataset import LeRobotDatasetMetadata

    meta = LeRobotDatasetMetadata(repo_id, root=str(root) if root else None)
    stats = meta.stats.get("observation.state")
    if not stats:
        return False
    return bool(np.all(np.asarray(stats["std"]) == 0.0))


def _observation(frame: np.ndarray, state: np.ndarray, task: str, device: str) -> dict:
    """Shape one camera frame the way the dataset presented it during training."""
    import torch

    image = torch.from_numpy(frame).permute(2, 0, 1).float().div(255.0).unsqueeze(0)
    return {
        "observation.images.webcam": image.to(device),
        "observation.state": torch.from_numpy(state).float().unsqueeze(0).to(device),
        "task": [task],
    }


class _Feeder:
    """Streams the current motor command on its own clock.

    The board's watchdog exists to stop a robot whose host has gone away, and it
    cannot tell that apart from a host busy inside a forward pass. This keeps the
    wire busy at the control rate no matter how long the policy takes, so the
    watchdog keeps meaning what it should. It is a daemon thread and holds no
    state the robot needs, so a dead process stops feeding and the board stops
    the wheels on its own.
    """

    def __init__(self, link: MBotLink, period: float):
        self._link = link
        self._period = period
        self._command = (0, 0)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> "_Feeder":
        self._thread.start()
        return self

    def set(self, m1: int, m2: int) -> None:
        with self._lock:
            self._command = (int(m1), int(m2))

    def _run(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                m1, m2 = self._command
            self._link.stream_pwm(m1, m2)
            time.sleep(self._period)

    def close(self) -> None:
        self.set(0, 0)
        self._stop.set()
        self._thread.join(timeout=1.0)
        self._link.drive_pwm(0, 0)


def _light_line(frame: np.ndarray, target: np.ndarray) -> str:
    """How far the room has drifted from the light the policy was trained under."""
    live = frame.reshape(-1, 3).mean(0)
    delta = live.mean() - target.mean()
    verdict = "match" if abs(delta) < 8 else ("too dark" if delta < 0 else "too bright")
    return (f"light {live.mean():.0f} vs {target.mean():.0f} trained  ({delta:+.0f}, {verdict})"
            f"   RGB {live[0]:.0f}/{live[1]:.0f}/{live[2]:.0f}"
            f" vs {target[0]:.0f}/{target[1]:.0f}/{target[2]:.0f}")


class _Episode:
    """A recorded episode played back in place of the camera.

    The point is to separate two failures that look identical from the outside.
    Driving from the camera exercises the whole chain at once - lens, lighting,
    encoding, policy, wiring - so when the robot does something aimless there is
    no way to tell a policy that never learned the task from a policy being fed
    something unlike anything it trained on.

    Feeding it frames from its own training data removes every variable except
    the policy and the wiring. The robot should then reproduce the episode: the
    frames are exactly the ones the demonstration was recorded against, and the
    recorded action for each is known, so predicted and demonstrated commands can
    be compared as it drives.

    This is open loop, and that is the one thing to keep in mind while watching.
    The frames advance on their own clock no matter where the robot actually
    goes, so drift is expected and means nothing; what matters is whether the
    commands match the demonstration.
    """

    def __init__(self, repo_id: str, root: Path | None, episode: int):
        from lerobot.datasets.lerobot_dataset import LeRobotDataset

        dataset = LeRobotDataset(repo_id, root=str(root) if root else None)
        lengths = list(dataset.meta.episodes["length"])
        if not 0 <= episode < len(lengths):
            raise ValueError(f"episode {episode} is outside 0..{len(lengths) - 1}")

        start = sum(lengths[:episode])
        self.task = dataset.meta.episodes["tasks"][episode][0]
        self.frames: list[np.ndarray] = []
        self.actions: list[np.ndarray] = []
        for k in range(lengths[episode]):
            item = dataset[start + k]
            image = item["observation.images.webcam"].numpy().transpose(1, 2, 0) * 255
            self.frames.append(image.astype(np.uint8))
            self.actions.append(item["action"].numpy().astype(np.float32))
        self.cursor = 0

    def __len__(self) -> int:
        return len(self.frames)

    @property
    def exhausted(self) -> bool:
        return self.cursor >= len(self.frames)

    def frame(self) -> np.ndarray | None:
        return None if self.exhausted else self.frames[self.cursor]

    def recorded(self) -> np.ndarray:
        index = min(self.cursor, len(self.actions) - 1)
        return self.actions[index]


def _widen(batch: dict, n: int) -> dict:
    """Repeat every entry n times, so one pass draws n independent chunks."""
    import torch

    out = {}
    for key, value in batch.items():
        if torch.is_tensor(value):
            out[key] = value.repeat(n, *([1] * (value.dim() - 1)))
        elif isinstance(value, list):
            out[key] = value * n
        else:
            out[key] = value
    return out


def _accepts_rtc(policy) -> bool:
    """Whether this policy's chunk predictor takes the RTC seam arguments."""
    signature = inspect.signature(policy.predict_action_chunk)
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in signature.parameters.values()):
        return True
    return "inference_delay" in signature.parameters


class _Planner:
    """Computes action chunks in a worker thread, so the control loop never waits.

    The control loop consumes actions from the chunk in hand at a steady 20 Hz.
    Once `RTC_EXECUTION_HORIZON` of them have been used it asks for the next
    chunk and carries on consuming; when the new chunk lands it replaces the old
    one, positioned past the actions that were executed while it was computed.

    The unexecuted tail of the current chunk goes back into the request as
    `prev_chunk_left_over`. That is what makes the seam continuous: RTC pins the
    new chunk to those already-committed actions and inpaints the rest, rather
    than jumping to a fresh trajectory that assumes the robot is somewhere it no
    longer is. It has to be the policy's own normalized output, not the
    unnormalized command, because the guidance is applied inside the denoiser.
    """

    def __init__(self, policy, preprocessor, postprocessor, device: str, period: float,
                 horizon: int = RTC_EXECUTION_HORIZON,
                 samples: int = 1):
        self._policy = policy
        self._pre = preprocessor
        self._post = postprocessor
        self._device = device
        self._period = period
        self._horizon = horizon

        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._request = None
        self._busy = False
        self._chunk = None       # (1, T, A), straight from the policy
        self._cursor = 0
        self._taken = 0          # actions used since this chunk landed
        # ACT's predict_action_chunk takes the batch alone, so the RTC seam
        # arguments are a TypeError there rather than a no-op. Asking the
        # policy once beats catching the failure every pass: a planner that
        # throws on every pass never produces a chunk, and the robot sits still
        # while the control loop reports itself healthy.
        self._rtc = _accepts_rtc(policy)
        self._samples = max(1, samples)
        # Ticks the last forward pass took, fed to RTC as inference_delay.
        # Measured rather than assumed, because it varies with the device.
        self._delay = 1
        self._generation = 0     # bumped on reset, to discard in-flight results
        self._latencies: list[float] = []
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> "_Planner":
        self._thread.start()
        return self

    @property
    def latencies(self) -> list[float]:
        with self._lock:
            return list(self._latencies)

    def should_plan(self) -> bool:
        with self._lock:
            if self._busy:
                return False
            if self._chunk is None:
                return True
            # Ask early by exactly the time the pass will take, so the new chunk
            # lands as the horizon runs out rather than a delay later. Without
            # this the cadence is horizon + delay, and the robot plans on a
            # staler frame than asked for.
            due = max(1, self._horizon - self._delay)
            return self._taken >= due or self._cursor >= self._chunk.shape[1]

    def submit(self, frame: np.ndarray, task: str, state: np.ndarray) -> None:
        with self._lock:
            if self._busy:
                return
            leftover = None
            if self._chunk is not None and self._cursor < self._chunk.shape[1]:
                leftover = self._chunk[:, self._cursor:, :].clone()
            self._request = (frame.copy(), task, state.copy(), leftover,
                             self._delay, self._generation)
            self._busy = True
        self._wake.set()

    def take(self) -> np.ndarray | None:
        """The next action, or None while the first chunk is still being computed."""
        with self._lock:
            if self._chunk is None or self._cursor >= self._chunk.shape[1]:
                return None
            step = self._chunk[:, self._cursor, :]
            self._cursor += 1
            self._taken += 1
        action = self._post(step).squeeze(0).float().cpu().numpy()
        return action.astype(np.float32)

    @property
    def busy(self) -> bool:
        """True while a forward pass is in flight."""
        with self._lock:
            return self._busy

    @property
    def taken(self) -> int:
        """Actions handed out since the current chunk landed."""
        with self._lock:
            return self._taken

    def is_empty(self) -> bool:
        """True while there is no plan to draw the next action from."""
        with self._lock:
            return self._chunk is None or self._cursor >= self._chunk.shape[1]

    def reset(self) -> None:
        """Drop the current plan. Any forward pass in flight is discarded."""
        with self._lock:
            self._chunk = None
            self._cursor = 0
            self._taken = 0
            self._request = None
            self._generation += 1
        self._policy.reset()

    def _run(self) -> None:
        while not self._stop.is_set():
            self._wake.wait()
            self._wake.clear()
            if self._stop.is_set():
                break

            with self._lock:
                request = self._request
                self._request = None
            if request is None:
                with self._lock:
                    self._busy = False
                continue

            frame, task, state, leftover, delay, generation = request
            # Skipping the head of a chunk is only right when RTC pinned it to
            # actions already executed. With no leftover - the first chunk of an
            # engagement, or every chunk in stop-and-go, where the plan is
            # dropped before each submit - it duplicates nothing and skipping
            # would discard commands the policy meant to issue.
            pinned = self._rtc and leftover is not None
            began = time.monotonic()
            try:
                batch = self._pre(_observation(frame, state, task, self._device))
                if self._samples > 1:
                    batch = _widen(batch, self._samples)
                    if leftover is not None:
                        leftover = leftover.repeat(self._samples, 1, 1)
                if self._rtc:
                    chunk = self._policy.predict_action_chunk(
                        batch,
                        inference_delay=delay,
                        prev_chunk_left_over=leftover,
                        execution_horizon=self._horizon,
                    )
                else:
                    chunk = self._policy.predict_action_chunk(batch)
            except Exception as exc:  # a failed pass must not kill the thread
                print(f"\ninference failed: {type(exc).__name__}: {exc}")
                with self._lock:
                    self._busy = False
                continue

            if self._samples > 1:
                # Element-wise across draws: the middle answer, not an average,
                # so one wild sample cannot drag the command with it.
                chunk = chunk.median(dim=0, keepdim=True).values

            took = time.monotonic() - began
            ticks = max(1, int(math.ceil(took / self._period)))
            with self._lock:
                self._busy = False
                self._latencies.append(took)
                self._delay = ticks
                # A reset while this was in flight means the instruction or the
                # engagement changed; the plan is about a situation that no
                # longer applies.
                if generation != self._generation:
                    continue
                self._chunk = chunk
                # The observation is `ticks` old by now. Where RTC pinned the
                # new chunk to the actions already executed, resuming past them
                # avoids repeating what the robot has done. Everywhere else the
                # chunk is an independent prediction and starts at zero.
                self._cursor = min(ticks, chunk.shape[1] - 1) if pinned else 0
                self._taken = 0

    def close(self) -> None:
        self._stop.set()
        self._wake.set()
        self._thread.join(timeout=2.0)


def rollout(config: RolloutConfig, robot: RobotConfig) -> int:
    import pygame

    from .camera import Camera
    from .ui import Viewer

    episode = None
    if config.replay_episode is not None:
        episode = _Episode(config.dataset_repo_id, config.dataset_root, config.replay_episode)
        print(f"Replaying episode {config.replay_episode}: {len(episode)} frames "
              f"({len(episode) / robot.control_hz:.1f}s), recorded task {episode.task!r}")
        print("  The camera is not used. Frames advance on their own clock, so the")
        print("  robot will drift from the scene it is being shown - that is expected.")
        print("  What matters is whether the commands match the demonstration.")

    tasks = list(config.tasks)
    if not tasks and episode is not None:
        tasks = [episode.task]
    if not tasks:
        print("No instruction to drive under; pass --task.")
        return 1

    print(f"Loading {config.policy_path} on {config.device} ...")
    policy, preprocessor, postprocessor = load_policy(config)

    frozen_state = state_is_constant(config.dataset_repo_id, config.dataset_root)
    if frozen_state:
        print("  trained without proprioception; observation.state stays zero")

    # Replayed frames come out of the dataset already transformed; only live
    # ones need it applying.
    arena = arena_transform(config.dataset_root) if episode is None else None
    if arena is not None:
        print(f"  arena rectified from the training dataset: frames -> {arena.shape[1]}x{arena.shape[0]}")

    target_light = training_brightness(config.dataset_repo_id, config.dataset_root)
    if target_light is not None and episode is None:
        print(f"  trained under brightness {target_light.mean():.0f} "
              f"(RGB {target_light[0]:.0f}/{target_light[1]:.0f}/{target_light[2]:.0f}); "
              "the overlay shows how the room compares")

    camera = None
    if episode is None:
        camera = Camera(
            robot.camera_index, robot.camera_width, robot.camera_height,
            robot.camera_name, robot.camera_map,
        )
        camera.open()
    viewer = Viewer(width=config.window, title="mbot - rollout")
    period = 1.0 / robot.control_hz

    print("The policy has the sticks. It starts stopped.")
    print("  space  engage / disengage the policy")
    if len(tasks) > 1:
        print(f"  1-{len(tasks)}    switch the instruction while it drives")
    print("  q      quit")
    for index, task in enumerate(tasks, start=1):
        print(f"  {index}  {task}")

    selected = 0
    engaged = False
    state = np.zeros(2, dtype=np.float32)
    action = np.zeros(2, dtype=np.float32)
    engaged_at = 0.0
    latencies: list[float] = []
    planner = None
    tracked: list[tuple[np.ndarray, np.ndarray]] = []

    try:
        with MBotLink(robot.port, watchdog_ms=robot.watchdog_ms, baud=robot.baud) as link:
            print(f"  board: {link.banner}")
            feeder = _Feeder(link, period).start()
            planner = _Planner(policy, preprocessor, postprocessor, config.device,
                               period, config.execution_horizon,
                               config.samples).start()
            # stop-and-go state: settle -> planning -> drive, repeating.
            phase, driven, settle_until = "settle", 0, None
            try:
                while True:
                    started = time.monotonic()
                    quit_now = False

                    for event in pygame.event.get():
                        if event.type == pygame.QUIT:
                            quit_now = True
                        elif event.type == pygame.KEYDOWN:
                            if event.key == pygame.K_q:
                                quit_now = True
                            elif event.key == pygame.K_SPACE:
                                engaged = not engaged
                                # Both directions drop the plan: actions computed
                                # before a pause are stale by the time it resumes.
                                planner.reset()
                                phase, driven, settle_until = "settle", 0, None
                                state[:] = 0.0
                                action[:] = 0.0
                                feeder.set(0, 0)
                                if engaged:
                                    engaged_at = time.monotonic()
                                    link.beep(880, 60)
                                else:
                                    link.beep(440, 90)
                            elif pygame.K_1 <= event.key <= pygame.K_9:
                                choice = event.key - pygame.K_1
                                if choice < len(tasks) and choice != selected:
                                    selected = choice
                                    # Without this the planned chunk keeps
                                    # driving to the old goal and the policy
                                    # looks like it is ignoring the words.
                                    planner.reset()
                                    print(f"  -> {tasks[selected]}")
                    if quit_now:
                        break

                    frame = episode.frame() if episode is not None else camera.latest()
                    if arena is not None and frame is not None:
                        frame = arena(frame)

                    if engaged and episode is not None and episode.exhausted:
                        print("  episode finished")
                        engaged = False
                        planner.reset()
                        feeder.set(0, 0)
                        action[:] = 0.0

                    if engaged and frame is not None and config.stop_and_go:
                        # Halt, settle, look, plan, drive - one chunk at a time.
                        # Nothing overlaps, so the observation the chunk was
                        # built from is still true when it starts executing.
                        if phase == "drive":
                            nxt = planner.take()
                            if nxt is not None:
                                action = nxt
                                if not frozen_state:
                                    state = action.copy()
                                left, right = robot.wheels(action)
                                feeder.set(*robot.to_pwm(left, right))
                                driven += 1
                                if episode is not None:
                                    tracked.append((action.copy(), episode.recorded().copy()))
                                    episode.cursor += 1
                            if driven >= config.execution_horizon or planner.is_empty():
                                phase, settle_until = "settle", None
                        elif phase == "settle":
                            feeder.set(0, 0)
                            action[:] = 0.0
                            if settle_until is None:
                                settle_until = time.monotonic() + config.settle_seconds
                            elif time.monotonic() >= settle_until:
                                # The chunk in hand was planned from a frame the
                                # robot has since driven away from; drop it and
                                # look again now that the wheels are still.
                                planner.reset()
                                planner.submit(frame, tasks[selected], state)
                                phase = "planning"
                        else:  # planning
                            feeder.set(0, 0)
                            action[:] = 0.0
                            if not planner.is_empty():
                                phase, driven = "drive", 0
                            elif not planner.busy:
                                # The submit was dropped because a pass from an
                                # earlier engagement was still running, and its
                                # result was discarded as stale. Nothing is
                                # coming; ask again rather than wait forever.
                                planner.submit(frame, tasks[selected], state)

                    elif engaged and frame is not None:
                        # Ask for the next chunk before the current one runs out,
                        # so the worker computes it while these actions execute.
                        if planner.should_plan():
                            planner.submit(frame, tasks[selected], state)

                        nxt = planner.take()
                        if nxt is not None:
                            action = nxt
                            if not frozen_state:
                                state = action.copy()
                            left, right = robot.wheels(action)
                            feeder.set(*robot.to_pwm(left, right))
                            if episode is not None:
                                tracked.append((action.copy(), episode.recorded().copy()))
                                episode.cursor += 1

                        if time.monotonic() - engaged_at > MAX_RUN_SECONDS:
                            print(f"  stopped after {MAX_RUN_SECONDS:.0f}s")
                            engaged = False
                            planner.reset()
                            feeder.set(0, 0)
                            action[:] = 0.0
                    elif not engaged:
                        feeder.set(0, 0)

                    latencies = planner.latencies
                    recent = latencies[-10:]
                    waiting = engaged and planner.is_empty()
                    viewer.show(
                        frame if frame is not None
                        else np.zeros((robot.camera_height, robot.camera_width, 3), np.uint8),
                        [
                            ((f"{phase.upper()} ..." if config.stop_and_go else
                              ("planning ..." if waiting else "DRIVING")) if engaged
                             else "stopped - space to engage"),
                            f"throttle {action[0]:+0.2f}   steer {action[1]:+0.2f}"
                            + (f"   plan {1000 * np.mean(recent):.0f} ms" if recent else ""),
                        ]
                        + ([
                            f"recorded {episode.recorded()[0]:+0.2f} {episode.recorded()[1]:+0.2f}"
                            f"   frame {episode.cursor}/{len(episode)}"
                        ] if episode is not None else [])
                        + ([_light_line(frame, target_light)]
                           if episode is None and frame is not None
                           and target_light is not None else [])
                        + [tasks[selected]],
                    )

                    elapsed = time.monotonic() - started
                    if elapsed < period:
                        time.sleep(period - elapsed)
            finally:
                planner.close()
                feeder.close()
    except KeyboardInterrupt:
        pass
    finally:
        if planner is not None:
            latencies = planner.latencies
        viewer.close()
        if camera is not None:
            camera.close()

    if latencies:
        arr = np.array(latencies) * 1000.0
        print(f"\n{len(arr)} plans   median {np.median(arr):.0f} ms   "
              f"p95 {np.percentile(arr, 95):.0f} ms   max {arr.max():.0f} ms")
        print(f"  re-planned every {config.execution_horizon} ticks "
              f"({1000 * period * config.execution_horizon:.0f} ms); "
              f"control period {1000 * period:.0f} ms")
        overruns = int((arr > 1000 * period * RTC_EXECUTION_HORIZON).sum())
        print(f"  plans that outlasted their horizon: {overruns}/{len(arr)}"
              + ("  (raise RTC_EXECUTION_HORIZON)" if overruns else ""))

    if tracked:
        predicted = np.array([p for p, _ in tracked])
        demonstrated = np.array([r for _, r in tracked])
        mae = np.abs(predicted - demonstrated).mean(0)
        print(f"\nagainst the demonstration, over {len(tracked)} commands:")
        print(f"  mean |error|   throttle {mae[0]:.3f}   steer {mae[1]:.3f}")
        for index, name in ((0, "throttle"), (1, "steer")):
            if demonstrated[:, index].std() > 1e-6 and predicted[:, index].std() > 1e-6:
                r = float(np.corrcoef(predicted[:, index], demonstrated[:, index])[0, 1])
                print(f"  correlation    {name:8} {r:+.3f}")
    return 0
