"""A scripted pick-and-place expert for the pinned SO101-Nexus environment.

This app deleted a 282-line scripted controller during the migration, along
with its own IK solver and a brute-force-calibrated grasp offset. This is not
that coming back. Upstream owns every hard part now:

  * **The IK is upstream's.** The environment is constructed in `pd_ee_pose`
    control mode, so an action is a TCP pose and `so101-nexus` solves for joint
    targets with its own damped-least-squares solver. Nothing here inverts a
    Jacobian.
  * **The success predicate is upstream's** — `info["success"]`, as everywhere
    else in this app.
  * **The scene is upstream's.** No MJCF, no physics tweak. In particular the
    contact model is left alone: hardening it (as other projects on this
    simulator have done) would make the recorded data describe a world the
    demo does not run in.

What is left is a waypoint sequence and four measured numbers. Every one was
established by sweeping against `info`, and the sweeps are reproducible with
`python -m vla_pick_and_place.run expert N`:

  * `GRASP_Z` is the load-bearing one. The jaws pinch ~9 mm below the TCP site
    (measured from MuJoCo contact positions, std 2.6 mm across seeds), so the
    TCP has to be commanded LOW. Measured over 12 seeds, grasp-then-lift
    survival: 0.006 -> 100%, 0.009 -> 83%, 0.012 -> 33%, 0.016 -> 0%. Six
    millimetres of aim is the difference between an expert and a coin flip.
  * `GRIP_CLOSED` is 0.0, not the actuator minimum. Commanding fully closed on
    a 25 mm cube makes the position servo extrude it: at -0.174 a *slower*
    carry scored worse than a fast one (0/12 vs 3/12), which is the signature
    of the cube being squeezed out over time rather than dropped.
  * Motion is interpolated, not commanded in one jump. A 108 mm step from
    grasp to carry height formed a grasp and then popped it within a few steps.
  * The gripper yaw is folded into +/-45 deg: a cube's grip is 90-deg
    symmetric, so beyond that there is nothing to align to.

Measured end to end on the stock environment: **79/100 seeds succeed**. The
recorder keeps only the successes, so the failure rate costs collection time,
not data quality.
"""

from __future__ import annotations

import numpy as np

from vla_pick_and_place.env.contract import (
    GRASP_STATE_INDEX,
    OBJECT_POSE_INDEX,
    TARGET_POSITION_INDEX,
)

# Gripper joint targets, radians. OPEN clears a 25 mm cube; CLOSED is a hold,
# not a crush — see the module docstring.
GRIP_OPEN = 1.2
GRIP_CLOSED = 0.0

# TCP heights above the cube centre / target disc, metres.
APPROACH_Z = 0.10
GRASP_Z = 0.006
CARRY_Z = 0.12
PLACE_Z = 0.030


def _state(obs) -> np.ndarray:
    """The privileged state vector, whatever shape the observation came in."""
    from vla_pick_and_place.config import OBS_ENV_STATE

    if isinstance(obs, dict):
        raw = obs.get(OBS_ENV_STATE, obs.get("state"))
    else:
        raw = obs
    return np.asarray(raw, dtype=np.float64)


def cube_pose(st: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Cube position and orientation quaternion (w, x, y, z)."""
    return st[OBJECT_POSE_INDEX:OBJECT_POSE_INDEX + 3].copy(), st[
        OBJECT_POSE_INDEX + 3:OBJECT_POSE_INDEX + 7
    ].copy()


def target_position(st: np.ndarray) -> np.ndarray:
    return st[TARGET_POSITION_INDEX:TARGET_POSITION_INDEX + 3].copy()


def is_grasped(st: np.ndarray) -> bool:
    return bool(st[GRASP_STATE_INDEX])


def cube_yaw(st: np.ndarray) -> float:
    """Cube yaw folded into +/-45 deg — a cube's grip is 90-deg symmetric."""
    from scipy.spatial.transform import Rotation

    _, (w, x, y, z) = cube_pose(st)
    yaw = Rotation.from_quat([x, y, z, w]).as_euler("xyz")[2]
    return (yaw + np.pi / 4) % (np.pi / 2) - np.pi / 4


def topdown_rotvec(yaw: float) -> np.ndarray:
    """TCP orientation, as `pd_ee_pose` wants it, with the jaws facing down.

    The approach axis is the TCP frame's local X — established by testing both
    candidates against a real grasp, not by reading the MJCF.
    """
    from scipy.spatial.transform import Rotation

    down = np.array([0.0, 0.0, -1.0])
    ref = np.array([np.cos(yaw), np.sin(yaw), 0.0])
    other = np.cross(down, ref)
    other /= np.linalg.norm(other)
    third = np.cross(down, other)
    m = np.column_stack([down, other, third])
    if np.linalg.det(m) < 0:  # keep the frame right-handed
        m[:, 1] *= -1.0
    return Rotation.from_matrix(m).as_rotvec()


class ScriptedExpert:
    """Drives `NexusPickAndPlace` (in `pd_ee_pose` mode) through one episode.

    `run` is a generator: it yields `(obs, joint_action, reward, info)` after
    every control step, so a recorder can log the same stream the demo would
    see. The yielded action is the SIX JOINT TARGETS the environment actually
    commanded — not the TCP pose this class sends — so a dataset built from it
    is directly executable by the app's `pd_joint_pos` contract.
    """

    def __init__(self, env):
        self.env = env

    def _tcp(self) -> np.ndarray:
        u = self.env.env.unwrapped
        return u.data.site_xpos[u._tcp_site_id].copy()

    def _step(self, pos, rotvec, grip):
        action = np.concatenate([pos, rotvec, [grip]]).astype(np.float32)
        obs, reward, terminated, truncated, info = self.env.step(action)
        return obs, self.env.commanded_joint_targets(), reward, terminated, truncated, info

    def _hold(self, pos, rotvec, grip, n):
        for _ in range(n):
            obs, joints, reward, term, trunc, info = self._step(pos, rotvec, grip)
            yield obs, joints, reward, info
            if term or trunc:
                return

    def _move(self, pos, rotvec, grip, n):
        """Ramp the commanded TCP setpoint from where it is now to `pos`."""
        start = self._tcp()
        goal = np.asarray(pos, dtype=np.float64)
        for i in range(n):
            alpha = (i + 1) / n
            yield from self._hold(start + alpha * (goal - start), rotvec, grip, 1)

    def run(self, seed: int):
        obs, info = self.env.reset(seed=seed)
        st = _state(obs)
        cube, _ = cube_pose(st)
        target = target_position(st)
        rotvec = topdown_rotvec(cube_yaw(st))

        plan = (
            (self._move, cube + [0, 0, APPROACH_Z], GRIP_OPEN, 30),
            (self._move, cube + [0, 0, GRASP_Z], GRIP_OPEN, 30),
            (self._hold, cube + [0, 0, GRASP_Z], GRIP_OPEN, 5),
            (self._hold, cube + [0, 0, GRASP_Z], GRIP_CLOSED, 35),
            (self._move, cube + [0, 0, CARRY_Z], GRIP_CLOSED, 45),
            (self._move, target + [0, 0, CARRY_Z], GRIP_CLOSED, 50),
            (self._move, target + [0, 0, PLACE_Z], GRIP_CLOSED, 35),
            (self._hold, target + [0, 0, PLACE_Z], GRIP_CLOSED, 8),
            (self._hold, target + [0, 0, PLACE_Z], GRIP_OPEN, 20),
            (self._move, target + [0, 0, CARRY_Z], GRIP_OPEN, 25),
        )
        for phase, pos, grip, n in plan:
            yield from phase(pos, rotvec, grip, n)


def evaluate(n_seeds: int = 30, start: int = 0) -> dict:
    """Success rate over a fixed seed band. The expert's own pass bar."""
    from vla_pick_and_place.env.nexus import NexusPickAndPlace

    wins, failures = 0, []
    with NexusPickAndPlace(control_mode="pd_ee_pose", cameras=False) as env:
        expert = ScriptedExpert(env)
        for seed in range(start, start + n_seeds):
            info = {}
            for _obs, _act, _rew, info in expert.run(seed):
                pass
            if info.get("success"):
                wins += 1
            else:
                failures.append(
                    {"seed": seed, "obj_to_target_dist": round(float(info["obj_to_target_dist"]), 3)}
                )
    return {
        "seeds": f"{start}..{start + n_seeds - 1}",
        "success": wins,
        "attempted": n_seeds,
        "success_rate": round(wins / n_seeds, 3),
        "failures": failures,
    }
