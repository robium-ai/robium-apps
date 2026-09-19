from __future__ import annotations

import json
import multiprocessing as mp
import queue
import threading
import time
import traceback

from act_aloha_cube_transfer.calibration import EVIDENCE_PATH
from act_aloha_cube_transfer.checkpoint import ensure_official_checkpoint
from act_aloha_cube_transfer.environment import (
    make_env,
    render_top_frame,
    step_manual_physics,
    validate_joint_targets,
)
from act_aloha_cube_transfer.policy import ACTCheckpoint, preferred_device
from act_aloha_cube_transfer.rollout import run_rollout
from act_aloha_cube_transfer.types import RolloutResult, RolloutStep


def _preview_worker(seed: int, output) -> None:
    try:
        env = make_env()
        try:
            observation, _ = env.reset(seed=seed)
            output.put(("frame", observation["pixels"]["top"]))
        finally:
            env.close()
    except BaseException:
        output.put(("error", traceback.format_exc()))


def _put_latest(channel, item) -> None:
    try:
        while True:
            channel.get_nowait()
    except queue.Empty:
        pass
    try:
        channel.put_nowait(item)
    except queue.Full:
        pass


def _manual_control_worker(seed: int, targets, commands, frames, status, stop) -> None:
    """Own the macOS renderer on this process's main thread for its full lifetime."""
    env = None
    try:
        env = make_env()
        env.reset(seed=int(seed))
        active_seed = int(seed)
        active_targets = validate_joint_targets(targets)
        frame_period = 1.0 / 30.0
        physics_period = 1.0 / 50.0
        next_frame = next_physics = time.perf_counter()
        status.put(("ready",))

        while not stop.is_set():
            try:
                while True:
                    command, command_seed, command_targets = commands.get_nowait()
                    if command == "pose":
                        if int(command_seed) != active_seed:
                            env.reset(seed=int(command_seed))
                            active_seed = int(command_seed)
                        active_targets = validate_joint_targets(command_targets)
                    elif command == "reset":
                        env.reset(seed=int(command_seed))
                        active_seed = int(command_seed)
                        active_targets = validate_joint_targets(command_targets)
            except queue.Empty:
                pass

            now = time.perf_counter()
            if now >= next_physics:
                state = step_manual_physics(env, active_targets)
                next_physics += physics_period
                if next_physics < now - physics_period:
                    next_physics = now + physics_period

            now = time.perf_counter()
            if now >= next_frame:
                frame = render_top_frame(env)
                _put_latest(frames, (frame, state, now))
                next_frame += frame_period
                if next_frame < now - frame_period:
                    next_frame = now + frame_period

            delay = min(next_physics, next_frame) - time.perf_counter()
            if delay > 0:
                stop.wait(delay)
    except BaseException:
        status.put(("error", traceback.format_exc()))
    finally:
        if env is not None:
            env.close()
        status.put(("stopped",))


class ManualController:
    """Persistent 50 Hz simulator with a latest-frame 30 Hz output stream."""

    def __init__(self, context=None):
        self._context = context or mp.get_context("spawn")
        self._guard = threading.Lock()
        self._commands = None
        self._frames = None
        self._status = None
        self._stop = None
        self._process = None

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.is_alive()

    def start(self, seed: int, targets) -> None:
        with self._guard:
            if self.running:
                self._send_pose(seed, targets)
                return
            self._commands = self._context.Queue(maxsize=1)
            self._frames = self._context.Queue(maxsize=1)
            self._status = self._context.Queue()
            self._stop = self._context.Event()
            self._process = self._context.Process(
                target=_manual_control_worker,
                args=(
                    int(seed),
                    tuple(float(value) for value in targets),
                    self._commands,
                    self._frames,
                    self._status,
                    self._stop,
                ),
                daemon=True,
            )
            self._process.start()
            try:
                message = self._status.get(timeout=30)
            except queue.Empty as exc:
                self._process.terminate()
                self._process.join(timeout=5)
                self._clear()
                raise RuntimeError("ALOHA live manual control timed out during startup") from exc
            if message[0] == "error":
                self._process.join(timeout=5)
                self._clear()
                raise RuntimeError(message[1])

    def _send_pose(self, seed: int, targets, *, reset: bool = False) -> None:
        values = tuple(float(value) for value in validate_joint_targets(targets))
        _put_latest(self._commands, ("reset" if reset else "pose", int(seed), values))

    def update(self, seed: int, targets) -> None:
        with self._guard:
            if not self.running:
                raise RuntimeError("start live manual control before moving a joint")
            self._send_pose(seed, targets)

    def reset(self, seed: int, targets) -> None:
        with self._guard:
            if not self.running:
                raise RuntimeError("start live manual control before resetting the pose")
            self._send_pose(seed, targets, reset=True)

    def next_frame(self, timeout: float = 2.0):
        if self._frames is None:
            raise RuntimeError("live manual control is not running")
        try:
            return self._frames.get(timeout=timeout)
        except queue.Empty as exc:
            if self._status is not None:
                try:
                    message = self._status.get_nowait()
                except queue.Empty:
                    message = None
                if message and message[0] == "error":
                    raise RuntimeError(message[1]) from exc
            raise RuntimeError("live manual-control frame timed out") from exc

    def stop(self) -> None:
        with self._guard:
            if self._process is None:
                return
            self._stop.set()
            self._process.join(timeout=5)
            if self._process.is_alive():
                self._process.terminate()
                self._process.join(timeout=5)
            self._clear()

    def _clear(self) -> None:
        self._process = None
        self._commands = None
        self._frames = None
        self._status = None
        self._stop = None


def _rollout_worker(model_path: str, device: str, seed: int, horizon: int, events, cancel) -> None:
    try:
        checkpoint = ACTCheckpoint(model_path, device=device)
        result = run_rollout(
            checkpoint,
            seed=seed,
            execution_horizon=horizon,
            on_step=events.put,
            should_abort=cancel.is_set,
        )
        events.put(result)
    except BaseException:
        events.put(("error", traceback.format_exc()))


def _health_worker(model_path: str, device: str, seed: int, output) -> None:
    try:
        checkpoint = ACTCheckpoint(model_path, device=device)
        env = make_env()
        try:
            observation, _ = env.reset(seed=seed)
            started = time.perf_counter()
            actions = checkpoint.predict_chunk(observation)
            elapsed = time.perf_counter() - started
            output.put(("ready", tuple(actions.shape), elapsed))
        finally:
            env.close()
    except BaseException:
        output.put(("error", traceback.format_exc()))


class EpisodeRunner:
    """Own subprocesses so macOS creates each GLFW context on a main thread."""

    def __init__(self, device: str | None = None):
        self.device = device or preferred_device()
        self.model_path = ensure_official_checkpoint()
        self.evidence = json.loads(EVIDENCE_PATH.read_text())
        self._context = mp.get_context("spawn")
        self._lock = threading.Lock()
        self._cancel_requested = threading.Event()
        self._cancel = None
        self._process = None
        self._manual = ManualController(self._context)

    def begin_run(self) -> None:
        self.stop_manual()
        self._cancel_requested.clear()

    def preview(self, seed: int):
        output = self._context.Queue()
        process = self._context.Process(target=_preview_worker, args=(int(seed), output), daemon=True)
        process.start()
        try:
            kind, payload = output.get(timeout=30)
        except queue.Empty as exc:
            process.terminate()
            raise RuntimeError("ALOHA preview timed out") from exc
        finally:
            process.join(timeout=5)
        if kind == "error":
            raise RuntimeError(payload)
        return payload

    def start_manual(self, seed: int, targets) -> None:
        if self._lock.locked():
            raise RuntimeError("manual controls are unavailable while a policy rollout is running")
        self._manual.start(seed, targets)

    def update_manual(self, seed: int, targets) -> None:
        self._manual.update(seed, targets)

    def reset_manual(self, seed: int, targets) -> None:
        self._manual.reset(seed, targets)

    def manual_frames(self):
        while self._manual.running:
            try:
                yield self._manual.next_frame()
            except RuntimeError:
                if not self._manual.running:
                    return
                raise

    def stop_manual(self) -> None:
        self._manual.stop()

    def cancel(self) -> None:
        self.stop_manual()
        self._cancel_requested.set()
        if self._cancel is not None:
            self._cancel.set()

    def healthcheck(self, seed: int) -> float:
        output = self._context.Queue()
        process = self._context.Process(
            target=_health_worker,
            args=(str(self.model_path), self.device, int(seed), output),
            daemon=True,
        )
        process.start()
        try:
            message = output.get(timeout=120)
        except queue.Empty as exc:
            process.terminate()
            raise RuntimeError("ACT health inference timed out") from exc
        finally:
            process.join(timeout=10)
        if message[0] == "error":
            raise RuntimeError(message[1])
        _, shape, elapsed = message
        if shape != (100, 14):
            raise RuntimeError(f"ACT health inference returned {shape}, expected (100, 14)")
        return float(elapsed)

    def run(self, *, seed: int, execution_horizon: int):
        if not self._lock.acquire(timeout=30):
            raise RuntimeError("a rollout is already in progress")
        events = self._context.Queue()
        self._cancel = self._context.Event()
        if self._cancel_requested.is_set():
            self._cancel.set()
        self._process = self._context.Process(
            target=_rollout_worker,
            args=(
                str(self.model_path),
                self.device,
                int(seed),
                int(execution_horizon),
                events,
                self._cancel,
            ),
            daemon=True,
        )
        self._process.start()
        try:
            while True:
                try:
                    event = events.get(timeout=30)
                except queue.Empty as exc:
                    if not self._process.is_alive():
                        raise RuntimeError("ALOHA rollout worker exited without a result") from exc
                    continue
                if isinstance(event, tuple) and event[0] == "error":
                    raise RuntimeError(event[1])
                if isinstance(event, RolloutResult):
                    return event
                if not isinstance(event, RolloutStep):
                    raise RuntimeError(f"unexpected rollout event: {type(event).__name__}")
                yield event
        finally:
            self._cancel.set()
            self._process.join(timeout=10)
            if self._process.is_alive():
                self._process.terminate()
                self._process.join(timeout=5)
            self._process = None
            self._cancel = None
            self._lock.release()
