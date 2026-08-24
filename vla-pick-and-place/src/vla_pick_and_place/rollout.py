"""Single-rollout coordinator shared by fake and real policy environments."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from PIL import Image

from vla_pick_and_place.config import MAX_STEPS, classify_prompt


@dataclass(frozen=True)
class Observation:
    frame: Image.Image
    policy_input: Any


@dataclass(frozen=True)
class EnvironmentStep:
    observation: Observation
    success: bool
    done: bool


@dataclass(frozen=True)
class RolloutEvent:
    step: int
    frame: Image.Image | None
    phase: str


@dataclass(frozen=True)
class RolloutResult:
    state_id: int
    seed: int
    prompt: str
    prompt_class: str
    success: bool | None
    cancelled: bool
    steps: int
    duration_seconds: float
    action_latency_ms: tuple[float, ...]
    frame_count: int


class RolloutBusyError(RuntimeError):
    pass


class Environment(Protocol):
    def reset(self, state_id: int, seed: int) -> Observation: ...

    def step(self, action: Any) -> EnvironmentStep: ...


class Policy(Protocol):
    def reset(self) -> None: ...

    def select_action(self, observation: Any, prompt: str) -> Any: ...


class DeterministicFakePolicy:
    """A no-network policy for orchestration, UI, and lifecycle tests."""

    def reset(self) -> None:
        return None

    def select_action(self, observation: Any, prompt: str) -> list[float]:
        del observation, prompt
        return [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -1.0]


class FixtureEnvironment:
    """Replays compact official task frames and supplies a fake simulator result."""

    def __init__(
        self, fixture_dir: Path, *, success: bool = True, episode_steps: int = 4
    ):
        self.fixture_dir = Path(fixture_dir)
        self.success = success
        self.episode_steps = episode_steps
        self._step = 0
        self._state_id = 0

    def _frame(self) -> Image.Image:
        fixtures = sorted(self.fixture_dir.glob("*.jpg"))
        if fixtures:
            return Image.open(
                fixtures[(self._state_id + self._step) % len(fixtures)]
            ).convert("RGB")
        color = ((37 + self._step * 19) % 255, (83 + self._state_id * 31) % 255, 149)
        return Image.new("RGB", (64, 64), color)

    def reset(self, state_id: int, seed: int) -> Observation:
        del seed
        self._state_id = state_id
        self._step = 0
        frame = self._frame()
        return Observation(frame=frame, policy_input={"frame": frame.copy()})

    def step(self, action: Any) -> EnvironmentStep:
        del action
        self._step += 1
        done = self._step >= self.episode_steps
        frame = self._frame()
        return EnvironmentStep(
            observation=Observation(frame=frame, policy_input={"frame": frame.copy()}),
            success=self.success if done else False,
            done=done,
        )


class RolloutRunner:
    def __init__(
        self, environment: Environment, policy: Policy, max_steps: int = MAX_STEPS
    ):
        self.environment = environment
        self.policy = policy
        self.max_steps = max_steps
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self.last_result: RolloutResult | None = None

    @property
    def busy(self) -> bool:
        return self._lock.locked()

    def cancel(self) -> None:
        self._cancel.set()

    def run(
        self,
        state_id: int,
        prompt_value: str,
        on_event: Callable[[RolloutEvent], None] | None = None,
    ) -> RolloutResult:
        if not self._lock.acquire(blocking=False):
            raise RolloutBusyError("one rollout is already running")
        try:
            prompt = classify_prompt(prompt_value)
            if not 0 <= state_id < 20:
                raise ValueError("state_id must be in [0, 19]")
            seed = 1000 + state_id
            self._cancel.clear()
            self.policy.reset()
            observation = self.environment.reset(state_id, seed)
            started = time.monotonic()
            frame_count = 1
            latencies: list[float] = []
            emit = on_event or (lambda event: None)
            emit(RolloutEvent(step=0, frame=observation.frame, phase="running"))

            success: bool | None = False
            cancelled = False
            steps = 0
            for step_index in range(1, self.max_steps + 1):
                if self._cancel.is_set():
                    cancelled = True
                    success = None
                    break
                action_started = time.perf_counter()
                action = self.policy.select_action(
                    observation.policy_input, prompt.text
                )
                latencies.append((time.perf_counter() - action_started) * 1000)
                transition = self.environment.step(action)
                observation = transition.observation
                steps = step_index
                frame_count += 1
                emit(RolloutEvent(step=steps, frame=observation.frame, phase="running"))
                if transition.done:
                    success = transition.success
                    break
            else:
                success = False

            result = RolloutResult(
                state_id=state_id,
                seed=seed,
                prompt=prompt.text,
                prompt_class=prompt.provenance,
                success=success,
                cancelled=cancelled,
                steps=steps,
                duration_seconds=time.monotonic() - started,
                action_latency_ms=tuple(latencies),
                frame_count=frame_count,
            )
            self.last_result = result
            emit(
                RolloutEvent(
                    step=steps,
                    frame=None,
                    phase="cancelled" if cancelled else "complete",
                )
            )
            return result
        finally:
            self._lock.release()
