"""Record scripted-expert demonstrations as a LeRobot dataset.

This is the app's answer to a problem the migration survey made concrete:
**no trained controller exists for the stock `MuJoCoPickAndPlace-v1` scene,
from anyone**, and neither published dataset was recorded in it — one has a
wood floor and an orange robot, the other a second target disc. Training
against someone else's scene is what produced the 0%-success checkpoint this
app used to ship.

So the data is generated here, in the exact pinned environment the demo runs,
and three choices keep it that way:

  * **Simulator units, not LeRobot motor units.** `observation.state` and
    `action` are joint angles in RADIANS — the environment's own action space.
    The published datasets record degrees plus a gripper percent, which needs
    a conversion at every boundary and silently corrupts the gripper channel
    if anyone reaches for `np.deg2rad`. A policy trained on this data emits
    actions that `env.step()` accepts directly.
  * **fps 50 = the real control rate.** `control_dt` is 0.02 s and one
    recorded frame is exactly one env step, so the dataset's fps is not a
    playback convention here — it is the truth.
  * **Successes only.** An episode is written only if `info["success"]` holds
    at the end. The expert clears ~79% of seeds; the rest cost collection
    time, not data quality.

Nothing here modifies the physics. Other projects on this simulator harden the
contact model to make the grasp easier; that would make the recording describe
a world the demo does not run in.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from vla_pick_and_place.config import (
    APP_ROOT,
    CAMERA_H,
    CAMERA_W,
    CONTROL_FPS,
    JOINT_NAMES,
    LOCAL_DATASET_REPO_ID,
    N_JOINTS,
    OBS_OVERHEAD,
    OBS_STATE,
    OBS_WRIST,
    TASK,
)

DEFAULT_ROOT = APP_ROOT / "outputs" / "dataset"


def features() -> dict:
    """The dataset schema. Mirrors the environment's observation contract."""
    joint_names = list(JOINT_NAMES)
    return {
        "observation.state": {
            "dtype": "float32",
            "shape": (N_JOINTS,),
            "names": joint_names,
        },
        "action": {"dtype": "float32", "shape": (N_JOINTS,), "names": joint_names},
        "observation.images.wrist": {
            "dtype": "video",
            "shape": (CAMERA_H, CAMERA_W, 3),
            "names": ["height", "width", "channel"],
        },
        "observation.images.overhead": {
            "dtype": "video",
            "shape": (CAMERA_H, CAMERA_W, 3),
            "names": ["height", "width", "channel"],
        },
        "reward": {"dtype": "float32", "shape": (1,), "names": None},
        "success": {"dtype": "float32", "shape": (1,), "names": None},
    }


def record(
    n_episodes: int = 50,
    *,
    repo_id: str = LOCAL_DATASET_REPO_ID,
    root: Path | None = None,
    start_seed: int = 0,
    max_attempts: int | None = None,
    progress=print,
) -> dict:
    """Collect `n_episodes` SUCCESSFUL expert episodes. Never pushes to the Hub.

    Returns a summary dict. Seeds are consumed in order from `start_seed`, so
    a rerun with the same start reproduces the same dataset exactly.
    """
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    from vla_pick_and_place.data.expert import ScriptedExpert
    from vla_pick_and_place.env.nexus import NexusPickAndPlace

    root = Path(root) if root is not None else DEFAULT_ROOT
    max_attempts = max_attempts if max_attempts is not None else n_episodes * 3

    dataset = LeRobotDataset.create(
        repo_id=repo_id,
        fps=CONTROL_FPS,
        features=features(),
        root=root,
        robot_type="so101",
        use_videos=True,
    )

    kept, attempted, discarded = 0, 0, []
    with NexusPickAndPlace(control_mode="pd_ee_pose") as env:
        expert = ScriptedExpert(env)
        seed = start_seed
        while kept < n_episodes and attempted < max_attempts:
            frames, info = [], {}
            for obs, joint_action, reward, info in expert.run(seed):
                frames.append(
                    {
                        OBS_STATE: np.asarray(obs[OBS_STATE], dtype=np.float32),
                        "action": np.asarray(joint_action, dtype=np.float32),
                        OBS_WRIST: np.asarray(obs[OBS_WRIST]),
                        OBS_OVERHEAD: np.asarray(obs[OBS_OVERHEAD]),
                        "reward": np.array([reward], dtype=np.float32),
                        "success": np.array(
                            [1.0 if info.get("success") else 0.0], dtype=np.float32
                        ),
                    }
                )
            attempted += 1
            if not info.get("success"):
                discarded.append(seed)
                seed += 1
                continue
            for frame in frames:
                dataset.add_frame({**frame, "task": TASK})
            dataset.save_episode()
            kept += 1
            progress(f"episode {kept}/{n_episodes} kept (seed {seed}, {len(frames)} frames)")
            seed += 1

    return {
        "repo_id": repo_id,
        "root": str(root),
        "episodes": kept,
        "attempted": attempted,
        "discarded_seeds": discarded,
        "success_rate": round(kept / attempted, 3) if attempted else 0.0,
        "seeds": f"{start_seed}..{seed - 1}",
        "fps": CONTROL_FPS,
        "units": "radians (absolute joint position) — the environment's own",
    }
