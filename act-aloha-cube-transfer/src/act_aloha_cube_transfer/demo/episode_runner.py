from __future__ import annotations

import json
import multiprocessing as mp
import queue
import threading
import time
import traceback

from act_aloha_cube_transfer.calibration import EVIDENCE_PATH
from act_aloha_cube_transfer.checkpoint import ensure_official_checkpoint
from act_aloha_cube_transfer.environment import make_env
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

    def begin_run(self) -> None:
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

    def cancel(self) -> None:
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
