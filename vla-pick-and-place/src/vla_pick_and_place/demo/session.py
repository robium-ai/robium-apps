"""What the dashboard runs: a live simulator you drive, or a recorded episode.

Two sources, kept structurally apart so the UI cannot blur them:

  * `SimWorker` steps the pinned SO101-Nexus environment for real. Every frame
    it emits came out of MuJoCo, every number came out of `info`.
  * `data.datasets.EpisodePlayer` replays a published recording. No `step()`
    is called and no policy runs.

A third source — a learned controller — has no implementation here on purpose.
`policy/controllers.py` has none available, and a mode that silently degrades
into one of the two above is exactly the thing this app is not allowed to do.

**Why a worker thread.** MuJoCo's GL context is thread-affine (CGL on macOS
especially): an environment built on one thread and rendered from another
deadlocks in `make_current`, forever, with no exception. Gradio runs each
request on whatever worker is free, so a shared env is a guaranteed hang and a
per-request env would throw away the arm pose between clicks — which makes
driving the arm by hand impossible. So the env gets one owner thread for its
whole life, and requests hand it commands over a queue. Construction, every
step, every render, and `close()` all happen on that one thread.
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from vla_pick_and_place.config import (
    EXPLORE_STEPS,
    OBS_OVERHEAD,
    OBS_STATE,
    OBS_WRIST,
)


@dataclass
class Frame:
    """One moment, from whichever source produced it."""

    source: str
    """'simulator' or 'dataset:<repo_id>#<episode>'. Rendered in the UI verbatim."""
    step: int
    total: int
    wrist: np.ndarray
    overhead: np.ndarray
    state: np.ndarray
    action: np.ndarray
    reward: float | None = None
    success: bool = False
    info: dict[str, Any] = field(default_factory=dict)
    units: str = "radians"
    done: bool = False


class WorkerError(RuntimeError):
    """The simulator thread failed; the original error is chained."""


class SimWorker:
    """Owns one `NexusPickAndPlace` on a dedicated thread for its whole life.

    Commands are `(callable, result_slot)` pairs posted to a queue; the owner
    thread runs them and hands back a value or the exception. Callers block on
    the result, so from the outside this reads like ordinary method calls that
    happen to always execute on the right thread.
    """

    def __init__(self):
        self._commands: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._serve, name="sim-worker", daemon=True)
        self._ready = threading.Event()
        self._boot_error: BaseException | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._abort = threading.Event()
        self._seed: int | None = None
        self._last_obs: dict[str, np.ndarray] | None = None
        self._last_info: dict[str, Any] = {}
        self._steps_taken = 0
        self.action_low: np.ndarray | None = None
        self.action_high: np.ndarray | None = None
        self.max_episode_steps = 0

    # --- lifecycle -----------------------------------------------------------

    def start(self, timeout: float = 120.0) -> SimWorker:
        self._thread.start()
        if not self._ready.wait(timeout):
            raise WorkerError(f"simulator thread did not come up within {timeout}s")
        if self._boot_error is not None:
            raise WorkerError("simulator thread failed to start") from self._boot_error
        return self

    def _serve(self) -> None:
        from vla_pick_and_place.env.nexus import NexusPickAndPlace

        try:
            env = NexusPickAndPlace()
            self.action_low = np.asarray(env.action_space.low, dtype=np.float32)
            self.action_high = np.asarray(env.action_space.high, dtype=np.float32)
            self.max_episode_steps = env.max_episode_steps
            self._env = env
        except BaseException as exc:  # noqa: BLE001 — reported to start()
            self._boot_error = exc
            self._ready.set()
            return
        self._ready.set()
        try:
            while not self._stop.is_set():
                try:
                    job, slot = self._commands.get(timeout=0.2)
                except queue.Empty:
                    continue
                try:
                    slot["value"] = job(env)
                except BaseException as exc:  # noqa: BLE001 — handed to the caller
                    slot["error"] = exc
                finally:
                    slot["done"].set()
        finally:
            env.close()

    def _call(self, job: Callable, timeout: float = 300.0):
        if self._stop.is_set():
            raise WorkerError("simulator worker is shut down")
        slot: dict[str, Any] = {"done": threading.Event()}
        self._commands.put((job, slot))
        if not slot["done"].wait(timeout):
            raise WorkerError(f"simulator command timed out after {timeout}s")
        if "error" in slot:
            raise WorkerError("simulator command failed") from slot["error"]
        return slot["value"]

    def run_on_env(self, job: Callable, timeout: float = 300.0):
        """Run `job(env)` on the owner thread and return its result.

        The supported door for anything that needs the env itself — the boot
        contract check, mainly. Touching the env from another thread instead
        would build a second GL context and deadlock the first render.
        """
        return self._call(job, timeout=timeout)

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=10)

    # --- state ---------------------------------------------------------------

    @property
    def busy(self) -> bool:
        return self._lock.locked()

    def request_abort(self) -> None:
        """Stop an in-flight run at its next step (page refresh / reclaim)."""
        self._abort.set()

    @property
    def seed(self) -> int | None:
        return self._seed

    @property
    def steps_taken(self) -> int:
        return self._steps_taken

    def joint_targets(self) -> list[float]:
        """Current joint positions — the pose the sliders should start from."""
        if self._last_obs is None:
            return [0.0] * 6
        return [float(v) for v in self._last_obs[OBS_STATE]]

    # --- operations ----------------------------------------------------------

    def reset(self, seed: int | None = None) -> Frame:
        def job(env):
            obs, info = env.reset(seed=seed)
            return obs, info

        obs, info = self._call(job)
        self._seed = seed
        self._last_obs, self._last_info = obs, info
        self._steps_taken = 0
        return self._frame(obs, env_action=obs[OBS_STATE], reward=None, info=info, step=0)

    def drive(self, targets, n_steps: int = 24):
        """Hold `targets` (radians, absolute joint positions) for `n_steps`.

        A generator: yields a `Frame` per control step so the caller can stream
        the motion instead of showing only the settled pose. This is the manual
        control path — the action sent is exactly what the operator dialled in,
        clipped to the actuator range, and nothing rewrites it.
        """
        if self._last_obs is None:
            self.reset(seed=0)
        action = np.clip(
            np.asarray(targets, dtype=np.float32), self.action_low, self.action_high
        )
        if not self._lock.acquire(timeout=30):
            raise WorkerError("the simulator is already running a command")
        self._abort.clear()
        try:
            for i in range(n_steps):
                if self._abort.is_set():
                    return
                obs, reward, terminated, truncated, info = self._call(
                    lambda env, a=action: env.step(a)
                )
                self._last_obs, self._last_info = obs, info
                self._steps_taken += 1
                done = terminated or truncated or i == n_steps - 1
                yield self._frame(
                    obs, env_action=action, reward=reward, info=info,
                    step=self._steps_taken, done=done,
                )
                if terminated or truncated:
                    return
        finally:
            self._lock.release()

    def hold(self, n_steps: int = EXPLORE_STEPS):
        """Let the scene settle at the current pose, streaming each step."""
        targets = self.joint_targets()
        yield from self.drive(targets, n_steps=n_steps)

    def _frame(self, obs, *, env_action, reward, info, step, done=False) -> Frame:
        return Frame(
            source="simulator",
            step=step,
            total=self.max_episode_steps,
            wrist=obs[OBS_WRIST],
            overhead=obs[OBS_OVERHEAD],
            state=np.asarray(obs[OBS_STATE], dtype=np.float32),
            action=np.asarray(env_action, dtype=np.float32),
            reward=reward,
            success=bool(info.get("success", False)),
            info=info,
            units="radians",
            done=done,
        )


def dataset_frames(player, *, stride: int = 1):
    """Replay a recorded episode as `Frame`s, labelled as a recording.

    `units` says `lerobot rows` because the recorded numbers are degrees plus
    gripper percent, not the simulator's radians — showing them on the same
    axes as a live run without saying so would be a lie of omission.
    """
    source = f"dataset:{player.pin.repo_id}#{player.episode}"
    total = len(player)
    for i in range(0, total, stride):
        row = player.frame(i)
        yield Frame(
            source=source,
            step=i,
            total=total,
            wrist=row.get(OBS_WRIST),
            overhead=row.get(OBS_OVERHEAD),
            state=row[OBS_STATE],
            action=row["action"],
            reward=row.get("reward"),
            success=bool(row.get("success", 0.0)),
            info={},
            units="lerobot rows (degrees + gripper percent)",
            done=i + stride >= total,
        )
