"""Checkpoint cache and abortable live-rollout bridge for the Gradio demo."""

from __future__ import annotations

import json
import queue
import threading
from pathlib import Path

from diffusion_policy_pusht import config, shapes
from diffusion_policy_pusht.rollout import (
    DiffusionCheckpoint,
    RolloutResult,
    RolloutStep,
    make_env,
)


class EpisodeRunner:
    """Loads Diffusion checkpoints lazily and serializes live runs."""

    def __init__(self, device: str | None = None):
        self.device = device or config.demo_device()
        self.manifest = json.loads(config.DEMO_LADDER_MANIFEST.read_text())
        if self.manifest.get("policy") != "diffusion":
            raise ValueError("demo manifest is not a Diffusion Policy manifest")
        if self.manifest.get("schema_version") != 4:
            raise ValueError("demo manifest is not the official-policy schema")
        self.models = {model["name"]: model for model in self.manifest["models"]}
        self.default_model = self.manifest["selected_model"]
        self.inference_modes = self.manifest["inference_modes"]
        self.default_inference_mode = self.manifest["default_inference_mode"]
        self._policies: dict[str, DiffusionCheckpoint] = {}
        self._lock = threading.Lock()
        self._cancel = threading.Event()

        self._load(self.default_model)
        self.preview(config.DEMO_DEFAULT_SHAPE, int(self.manifest["live_seed"]))

    def _load(self, model: str) -> DiffusionCheckpoint:
        if model not in self.models:
            raise ValueError(f"unknown model {model!r}; choose from {list(self.models)}")
        if model not in self._policies:
            path = config.APP_ROOT / self.models[model]["checkpoint"]
            self._policies[model] = DiffusionCheckpoint(path, device=self.device)
        return self._policies[model]

    @property
    def busy(self) -> bool:
        return self._lock.locked()

    def cancel(self) -> None:
        self._cancel.set()

    @staticmethod
    def preview(shape: str, seed: int):
        if shape not in shapes.SHAPES:
            raise ValueError(f"unknown shape {shape!r}; choose from {list(shapes.SHAPES)}")
        env = make_env(shape)
        try:
            obs, _ = env.reset(seed=int(seed))
            return obs["pixels"]
        finally:
            env.close()

    def run(self, model: str, *, inference_mode: str, shape: str, seed: int):
        if model not in self.models:
            raise ValueError(f"unknown model {model!r}; choose from {list(self.models)}")
        if inference_mode not in self.inference_modes:
            raise ValueError(
                f"unknown inference mode {inference_mode!r}; choose from {list(self.inference_modes)}"
            )
        if not self._lock.acquire(timeout=30):
            raise RuntimeError("a rollout is already in progress")
        self._cancel.clear()
        events: queue.Queue[RolloutStep | RolloutResult | BaseException] = queue.Queue()
        thread: threading.Thread | None = None
        try:
            checkpoint = self._load(model)
            checkpoint.configure(
                n_action_steps=int(self.models[model]["n_action_steps"]),
                num_inference_steps=int(
                    self.inference_modes[inference_mode]["num_inference_steps"]
                ),
            )

            def worker() -> None:
                try:
                    result = checkpoint.run(
                        seed=int(seed),
                        shape=shape,
                        on_step=events.put,
                        should_abort=self._cancel.is_set,
                    )
                    events.put(result)
                except BaseException as exc:  # surface worker errors in Gradio's generator
                    events.put(exc)

            thread = threading.Thread(target=worker, name=f"rollout-{model}-{seed}", daemon=True)
            thread.start()
            while True:
                event = events.get()
                if isinstance(event, BaseException):
                    raise event
                if isinstance(event, RolloutResult):
                    return event
                yield event
        finally:
            self._cancel.set()
            if thread is not None:
                thread.join(timeout=30)
            self._lock.release()
