"""Interactive scene setting with a policy you can start, pause, and restart.

This mirrors how the real rig will be used: put the block somewhere, point the
robot roughly at it, let the policy run, stop it when it goes wrong, move things,
and go again. Being able to construct a specific situation by hand - block hard
left, robot facing away - probes a policy far faster than waiting for random
resets to produce that case.

While paused, physics is frozen and bodies are teleported directly. Unpausing
clears the policy's action queue, so it plans from what it sees now rather than
replaying a chunk predicted before you moved anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch

from .config import CONTROL_HZ
from .record import TASK
from .rollout import RolloutConfig, load_policy, _observation
from .sim import PushEnv
from .ui import Viewer

# Keep placements inside the walls.
X_LIMIT, Y_LIMIT = 0.46, 0.36

NUDGE_M = 0.006      # per frame while an arrow is held
TURN_RAD = 0.05      # per frame while a rotate key is held


@dataclass
class InteractiveConfig:
    policy_path: str
    dataset_repo_id: str
    dataset_root: Path | None = None
    render_size: int = 256
    window: int = 700
    device: str = "mps"
    seed: int | None = None
    # MuJoCo pauses while the policy thinks, so a slow policy plans from a frame
    # that is still true when its chunk lands. Hardware gives no such courtesy.
    realtime: bool = False
    # Charge a fixed cost per forward pass rather than the measured one, so a
    # latency can be dialled in rather than inherited from this laptop.
    latency_ms: float | None = None
    # Drive a chunk, halt, settle, then look and plan again - the hardware flag
    # of the same name. The clock keeps running through the halt: the robot
    # stops, the world does not.
    stop_and_go: bool = False
    settle_seconds: float = 0.5
    # None keeps whatever the checkpoint trained with.
    n_action_steps: int | None = None


def interactive(config: InteractiveConfig) -> int:
    import pygame

    policy, preprocessor, postprocessor = load_policy(
        RolloutConfig(
            policy_path=config.policy_path,
            dataset_repo_id=config.dataset_repo_id,
            dataset_root=config.dataset_root,
            device=config.device,
            # load_policy applies this to the checkpoint's config, so it has to
            # travel with it; a field left behind here is a flag silently
            # ignored.
            n_action_steps=config.n_action_steps,
        )
    )

    viewer = Viewer(size=config.window, title="interactive")
    period = 1.0 / CONTROL_HZ
    scale = config.render_size / config.window

    running_policy = False
    state = np.zeros(2, dtype=np.float32)
    action = np.zeros(2, dtype=np.float32)
    dragging: str | None = None

    print("space  start / pause the policy")
    print("drag   left button moves the block, right button moves the robot")
    print("arrows move the robot     , .  rotate it")
    print("r      randomize the layout        q  quit")

    # select_action pops from a queue and only runs a forward pass when it
    # empties, so the latency falls on every n_action_steps-th tick.
    n_action_steps = max(1, int(getattr(policy.config, "n_action_steps", 1)))
    held = np.zeros(2, dtype=np.float32)
    plan_tick = 0
    stop_cmd = np.zeros(2, dtype=np.float32)
    settle_ticks = max(1, int(round(config.settle_seconds * CONTROL_HZ)))
    phase, settle_left, drive_left = "settle", settle_ticks, 0

    with PushEnv(render_size=config.render_size, seed=config.seed) as env:
        frame = env.reset(seed=config.seed)
        try:
            while True:
                import time

                started = time.monotonic()

                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        raise KeyboardInterrupt
                    if event.type == pygame.MOUSEBUTTONDOWN:
                        dragging = "block" if event.button == 1 else "robot"
                    elif event.type == pygame.MOUSEBUTTONUP:
                        dragging = None
                    elif event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_q:
                            raise KeyboardInterrupt
                        if event.key == pygame.K_SPACE:
                            running_policy = not running_policy
                            if running_policy:
                                # Plan from the scene as it is now, not from a
                                # chunk predicted before it was rearranged.
                                policy.reset()
                                plan_tick = 0
                                phase, settle_left = "settle", settle_ticks
                                state = np.zeros(2, dtype=np.float32)
                        elif event.key == pygame.K_r:
                            frame = env.reset()
                            running_policy = False

                if dragging is not None:
                    mouse = pygame.mouse.get_pos()
                    target = env.pixel_to_world(mouse[0] * scale, mouse[1] * scale)
                    x = float(np.clip(target[0], -X_LIMIT, X_LIMIT))
                    y = float(np.clip(target[1], -Y_LIMIT, Y_LIMIT))
                    if dragging == "block":
                        env.place_block(x, y)
                    else:
                        env.place_robot(x, y)
                    running_policy = False

                keys = pygame.key.get_pressed()
                if not running_policy:
                    _nudge_robot(env, keys, pygame)

                if running_policy:

                    def think(carry_cost: bool):
                        """One pass, and the ticks the world spends on it."""
                        batch = preprocessor(_observation(frame, state, config.device))
                        began = time.perf_counter()
                        with torch.no_grad():
                            raw = policy.select_action(batch)
                        measured_ms = (time.perf_counter() - began) * 1000.0
                        act = postprocessor(raw).squeeze(0).float().cpu().numpy()
                        if not carry_cost:
                            return act, 0
                        if config.latency_ms is not None:
                            cost = config.latency_ms
                        elif config.realtime:
                            cost = measured_ms
                        else:
                            cost = 0.0
                        return act, int(cost / (period * 1000.0))

                    if config.stop_and_go:
                        if phase == "settle":
                            frame = env.step(stop_cmd)
                            settle_left -= 1
                            if settle_left <= 0:
                                phase = "plan"
                        elif phase == "plan":
                            # Look and plan standing still, so the frame is
                            # still true when the chunk built from it runs.
                            policy.reset()
                            action, lag = think(True)
                            for _ in range(lag):
                                frame = env.step(stop_cmd)
                            frame = env.step(action)
                            state = action.astype(np.float32)
                            drive_left = n_action_steps - 1
                            phase = "drive"
                        else:
                            action, _ = think(False)
                            frame = env.step(action)
                            state = action.astype(np.float32)
                            drive_left -= 1
                            if drive_left <= 0:
                                phase, settle_left = "settle", settle_ticks
                        held = action.astype(np.float32)
                    else:
                        action, lag = think(plan_tick % n_action_steps == 0
                                            or config.latency_ms is None)
                        # Ticks that pass while the policy is thinking. The robot
                        # holds its last command through them, as the hardware
                        # feeder does, and the block keeps moving.
                        for _ in range(lag):
                            frame = env.step(held)
                        plan_tick += 1
                        frame = env.step(action)
                        held = action.astype(np.float32)
                        state = action.astype(np.float32)
                else:
                    frame = env.observe()

                distance = float(np.linalg.norm(env.body_xy("block") - np.array([0.35, 0.0])))
                viewer.show(
                    frame,
                    [
                        (f"{phase.upper()}  (space to pause)" if config.stop_and_go
                         else "RUNNING  (space to pause)")
                        if running_policy else "PAUSED  (space to run)",
                        f"throttle {action[0]:+0.2f}   steer {action[1]:+0.2f}",
                        f"block {distance:0.3f} m from goal",
                    ],
                )

                elapsed = time.monotonic() - started
                if elapsed < period:
                    time.sleep(period - elapsed)
        except KeyboardInterrupt:
            pass
        finally:
            viewer.close()
    return 0


def _nudge_robot(env: PushEnv, keys, pygame) -> None:
    """Arrow keys translate the robot; comma and period turn it."""
    position = env.body_xy("chassis")
    dx = float(keys[pygame.K_RIGHT]) - float(keys[pygame.K_LEFT])
    dy = float(keys[pygame.K_UP]) - float(keys[pygame.K_DOWN])
    turn = float(keys[pygame.K_PERIOD]) - float(keys[pygame.K_COMMA])
    if dx == 0.0 and dy == 0.0 and turn == 0.0:
        return
    env.place_robot(
        float(np.clip(position[0] + dx * NUDGE_M, -X_LIMIT, X_LIMIT)),
        float(np.clip(position[1] + dy * NUDGE_M, -Y_LIMIT, Y_LIMIT)),
        yaw=env.robot_yaw() + turn * TURN_RAD,
    )
