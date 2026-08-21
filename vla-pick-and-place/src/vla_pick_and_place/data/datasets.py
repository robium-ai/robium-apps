"""Published SO101-Nexus demonstrations: pinned, verified, and playable.

This app records no demonstrations of its own. It plays back published ones,
which makes provenance the whole problem: a LeRobot dataset that loads cleanly
and has the right feature shapes can still have been recorded in a *different
scene*, and nothing in its metadata says so. Two datasets exist for
`MuJoCoPickAndPlace-v1` and exactly that difference separates them.

`verify()` is the check that separates them, and it is deliberately in two
parts:

  * a **schema** check — feature shapes, camera keys, state/action width, task
    text, episode boundaries — which both datasets pass; and
  * a **scene** check — mean per-channel colour of a real dataset frame versus
    a freshly rendered frame from the pinned environment — which only the
    matching one passes.

The schema check alone would have shipped a dashboard playing an orange robot
on a wooden floor next to a live yellow robot on a grey floor and called both
"the environment".

Units, which are also not visible in the schema: dataset rows are LeRobot
convention (body joints in DEGREES, gripper as percent of jaw travel) while
the env action space is radians. `rows_to_sim_qpos` routes through
so101-nexus's published converter rather than a local deg2rad.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from vla_pick_and_place.config import (
    CAMERA_H,
    CAMERA_W,
    DATASET_ALT_REPO_ID,
    DATASET_ALT_REVISION,
    DATASET_REPO_ID,
    DATASET_REVISION,
    N_JOINTS,
    OBS_OVERHEAD,
    OBS_STATE,
    OBS_WRIST,
    TASK,
)


@dataclass(frozen=True)
class DatasetPin:
    """A published dataset, pinned, with what is known about how it matches."""

    repo_id: str
    revision: str
    label: str
    camera_map: dict[str, str]
    """Dataset camera key -> this app's camera key. Empty when unidentified."""
    scene_reference_camera: str
    """Which mapped camera the scene check may use. Must be a STATIC view.

    Only a fixed camera can answer "is this the same scene": the wrist camera
    is bolted to the arm AND its FOV, pitch, and mount offset are randomized
    per reset by design, so two frames of the same scene differ by however far
    the arm has moved. Measured on the matching dataset: overhead sits 0.002
    from a live render, wrist sits 0.108 — the wrist number is arm pose, not
    provenance. Empty means no camera on this pin can be used.
    """
    scene_verified: bool
    """True only if its frames were compared against a live render and matched."""
    note: str
    fps: int
    episodes: int


PRIMARY = DatasetPin(
    repo_id=DATASET_REPO_ID,
    revision=DATASET_REVISION,
    label="SO101-Nexus maintainer demonstrations",
    camera_map={
        "observation.images.wrist": OBS_WRIST,
        "observation.images.overhead": OBS_OVERHEAD,
    },
    scene_reference_camera=OBS_OVERHEAD,
    scene_verified=True,
    note=(
        "Recorded by the so101-nexus maintainer in this exact environment. "
        "Ships meta/so101_nexus_env.json (the env config used), reward and "
        "success channels, and env-native observation component names. Ten "
        "episodes: a reference and a playback source, not training data."
    ),
    fps=30,
    episodes=10,
)

# Registered, not adopted. See config.DATASET_ALT_REPO_ID for why the pixels
# disqualify it as a stand-in for this environment's demonstrations.
ALTERNATE = DatasetPin(
    repo_id=DATASET_ALT_REPO_ID,
    revision=DATASET_ALT_REVISION,
    label="molmoact2 scripted-expert set (different scene)",
    camera_map={},
    scene_reference_camera="",
    scene_verified=False,
    note=(
        "500 scripted-expert episodes with a published collector and a trained "
        "MolmoAct2 checkpoint — the strongest available training material for "
        "this task. But its frames are not this environment's: wood-textured "
        "ground, orange robot, and an angled side view where so101-nexus's "
        "OverheadCamera is top-down, so its collector overrode the scene "
        "config. Its cameras are also named cam0/cam1, which carries no view "
        "identity. Reproduce its env config before training or evaluating "
        "against it."
    ),
    fps=33,
    episodes=500,
)

REGISTRY = {PRIMARY.repo_id: PRIMARY, ALTERNATE.repo_id: ALTERNATE}


def load(pin: DatasetPin = PRIMARY, episodes: list[int] | None = None):
    """Open a pinned dataset at its pinned revision. Never reads `main`."""
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    return LeRobotDataset(pin.repo_id, revision=pin.revision, episodes=episodes)


def rows_to_sim_qpos(rows, gripper_limits_rad=None):
    """Decode dataset rows (degrees + gripper percent) into simulator radians.

    Delegates to so101-nexus's `dataset_row_to_sim_qpos`, which knows that the
    six-vector mixes units — a whole-vector `np.deg2rad` silently corrupts the
    gripper channel.
    """
    from so101_nexus.lerobot_dataset import (
        SO101_GRIPPER_LIMITS_RAD,
        dataset_row_to_sim_qpos,
    )

    limits = gripper_limits_rad or SO101_GRIPPER_LIMITS_RAD
    return dataset_row_to_sim_qpos(np.asarray(rows, dtype=np.float64), gripper_limits_rad=limits)


def _to_hwc_uint8(frame) -> np.ndarray:
    """LeRobot hands back CHW float in [0,1]; the app's frames are HWC uint8."""
    arr = np.asarray(frame)
    if arr.ndim == 3 and arr.shape[0] == 3:
        arr = arr.transpose(1, 2, 0)
    if arr.dtype != np.uint8:
        arr = (np.clip(arr, 0.0, 1.0) * 255.0).astype(np.uint8)
    return arr


@dataclass
class VerifyResult:
    pin: DatasetPin
    schema_ok: bool = False
    scene_ok: bool | None = None
    """None when no live render was supplied to compare against."""
    problems: list[str] = field(default_factory=list)
    measured: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.schema_ok and self.scene_ok is not False

    def raise_if_bad(self) -> VerifyResult:
        if not self.ok:
            raise DatasetMismatch(
                f"{self.pin.repo_id}@{self.pin.revision[:8]} does not match this "
                "environment:\n  - " + "\n  - ".join(self.problems)
            )
        return self


class DatasetMismatch(RuntimeError):
    """A pinned dataset disagrees with the environment the app runs."""


# Mean per-channel colour distance above which two frames are not the same
# scene, measured on the STATIC overhead view only (see
# `DatasetPin.scene_reference_camera`). The matching dataset's overhead frame
# sits 0.002 from a live render; the mismatched dataset's scene is wood-brown
# against grey and sits an order of magnitude further out. 0.05 leaves the
# match a 20x margin while staying far below any real scene change — this is
# a scene check, not pixel equality, so cube placement and arm pose are
# expected to differ.
SCENE_COLOR_TOLERANCE = 0.05


def verify(pin: DatasetPin = PRIMARY, reference_frames: dict[str, np.ndarray] | None = None) -> VerifyResult:
    """Check a pinned dataset against the environment contract.

    `reference_frames` maps this app's camera keys to freshly rendered uint8
    HWC frames from the live environment. Pass them to get the scene check;
    omit them (in a test with no GL, say) and only the schema check runs, with
    `scene_ok` left None rather than quietly reported as a pass.
    """
    result = VerifyResult(pin=pin)
    ds = load(pin, episodes=[0])
    meta = ds.meta

    def fail(msg: str) -> None:
        result.problems.append(msg)

    features = meta.features
    for key, want_shape in (("observation.state", [N_JOINTS]), ("action", [N_JOINTS])):
        if key not in features:
            fail(f"features: {key} missing")
        elif list(features[key]["shape"]) != want_shape:
            fail(f"features.{key}.shape: {list(features[key]['shape'])}, expected {want_shape}")

    dataset_cams = list(meta.camera_keys)
    if len(dataset_cams) != 2:
        fail(f"camera_keys: {dataset_cams}, expected two cameras")
    for cam in dataset_cams:
        shape = list(features[cam]["shape"])
        if shape != [CAMERA_H, CAMERA_W, 3]:
            fail(f"features.{cam}.shape: {shape}, expected {[CAMERA_H, CAMERA_W, 3]}")

    if not pin.camera_map:
        fail(
            f"camera identity: {dataset_cams} carry no view identity, so neither "
            f"can be mapped onto {OBS_WRIST}/{OBS_OVERHEAD}"
        )
    else:
        for src, dst in pin.camera_map.items():
            if src not in dataset_cams:
                fail(f"camera_map: {src} -> {dst} but the dataset has {dataset_cams}")

    tasks = [str(t) for t in meta.tasks.index]
    if TASK not in tasks:
        fail(f"task text: {tasks}, expected {TASK!r}")

    if meta.fps != pin.fps:
        fail(f"fps: {meta.fps}, expected {pin.fps}")
    if meta.total_episodes != pin.episodes:
        fail(f"total_episodes: {meta.total_episodes}, expected {pin.episodes}")

    if ds.num_frames <= 0:
        fail("episode 0 has no frames")

    result.measured = {
        "fps": meta.fps,
        "total_episodes": meta.total_episodes,
        "episode_0_frames": int(ds.num_frames),
        "camera_keys": dataset_cams,
        "tasks": tasks,
        "state_shape": list(features["observation.state"]["shape"]),
        "action_shape": list(features["action"]["shape"]),
    }
    result.schema_ok = not result.problems

    if reference_frames:
        ref_key = pin.scene_reference_camera
        src_key = next((s for s, d in pin.camera_map.items() if d == ref_key), None)
        if not ref_key or src_key is None or ref_key not in reference_frames:
            result.scene_ok = False
            fail(
                "scene appearance: this dataset exposes no static camera that can "
                "be compared against a live render, so its scene cannot be "
                "confirmed to be this environment's"
            )
        else:
            got = _to_hwc_uint8(ds[0][src_key]).astype(np.float32) / 255.0
            want = np.asarray(reference_frames[ref_key], dtype=np.float32) / 255.0
            distance = float(
                np.abs(got.reshape(-1, 3).mean(0) - want.reshape(-1, 3).mean(0)).mean()
            )
            result.measured["scene_color_distance"] = {ref_key: round(distance, 4)}
            result.scene_ok = distance <= SCENE_COLOR_TOLERANCE
            if not result.scene_ok:
                fail(
                    f"scene appearance {ref_key}: mean colour distance {distance:.3f} "
                    f"from a live render exceeds {SCENE_COLOR_TOLERANCE} — this "
                    "dataset was recorded in a differently configured scene"
                )

    return result


class EpisodePlayer:
    """Streams one recorded episode as frames the dashboard can render.

    Playback, and labelled as playback everywhere it surfaces. It does not
    touch the simulator: no `step()` is called, no policy runs, and the frames
    are the recorded video, not a re-render. That distinction is the reason
    this is a separate class from the live session rather than a mode flag on
    it.
    """

    def __init__(self, pin: DatasetPin = PRIMARY, episode: int = 0):
        self.pin = pin
        self.episode = episode
        self._ds = load(pin, episodes=[episode])
        self.n_frames = int(self._ds.num_frames)
        self.fps = int(self._ds.meta.fps)

    def __len__(self) -> int:
        return self.n_frames

    def frame(self, index: int) -> dict[str, Any]:
        """One recorded frame, in this app's observation key names.

        `observation.state` and `action` stay in the dataset's own units
        (degrees + gripper percent) — converting them to radians here would
        make the numbers on screen disagree with the dataset card. Callers
        that need simulator units go through `rows_to_sim_qpos`.
        """
        row = self._ds[int(index)]
        out: dict[str, Any] = {
            OBS_STATE: np.asarray(row["observation.state"], dtype=np.float32),
            "action": np.asarray(row["action"], dtype=np.float32),
        }
        for src, dst in self.pin.camera_map.items():
            out[dst] = _to_hwc_uint8(row[src])
        for extra in ("reward", "success"):
            if extra in row:
                out[extra] = float(np.asarray(row[extra]).reshape(-1)[0])
        return out

    def episodes_available(self) -> int:
        return int(self._ds.meta.total_episodes)
