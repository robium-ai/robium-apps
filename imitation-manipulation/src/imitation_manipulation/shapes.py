"""Named block geometries for the PushShape env.

T is byte-identical to gym-pusht's add_tee(scale=30, length=4) — it IS the
training distribution; L/I/Z are out-of-distribution probes. All rects are
convex quads in the T's local frame, non-overlapping (shapely coverage math
assumes it), edge-sharing allowed. gym-pusht derives BOTH the coverage
metric and the goal-zone silhouette from block.shapes, so every shape gets
a correctly-shaped goal and a meaningful reward for free.
"""

import gymnasium as gym
import pygame
import pymunk
from gym_pusht.envs.pusht import PushTEnv

# fmt: off
SHAPES = {
    "T": [  # upstream add_tee: 120x30 bar + 30x90 stem
        [(-60, 30), (60, 30), (60, 0), (-60, 0)],
        [(-15, 30), (-15, 120), (15, 120), (15, 30)],
    ],
    "L": [  # 30x120 stem + 60x30 foot (edge-shared at x=15)
        [(-15, 0), (15, 0), (15, 120), (-15, 120)],
        [(15, 90), (75, 90), (75, 120), (15, 120)],
    ],
    "I": [  # single 30x150 bar
        [(-15, 0), (15, 0), (15, 150), (-15, 150)],
    ],
    "Z": [  # two 90x30 bars, offset, edge-shared at y=30
        [(-60, 0), (30, 0), (30, 30), (-60, 30)],
        [(-30, 30), (60, 30), (60, 60), (-30, 60)],
    ],
}
# fmt: on

ENV_ID = "imitation_manipulation/PushShape-v0"


def _add_block(space, position, angle, rects, color="LightSlateGray"):
    """gym-pusht's add_tee generalized to any list of convex quads."""
    mass = 1
    body = pymunk.Body(mass, sum(pymunk.moment_for_poly(mass, r) for r in rects))
    shapes_ = []
    for r in rects:
        s = pymunk.Poly(body, r)
        s.color = pygame.Color(color)
        s.filter = pymunk.ShapeFilter(mask=pymunk.ShapeFilter.ALL_MASKS())
        shapes_.append(s)
    body.center_of_gravity = sum(
        (s.center_of_gravity for s in shapes_), pymunk.Vec2d(0, 0)
    ) / len(shapes_)
    body.angle = angle
    body.position = position
    body.friction = 1
    space.add(body, *shapes_)
    return body, shapes_


class PushShapeEnv(PushTEnv):
    """PushT with the block geometry swapped by name. shape='T' == upstream."""

    def __init__(self, shape="T", **kwargs):
        if shape not in SHAPES:
            raise ValueError(f"unknown shape {shape!r}; choose from {list(SHAPES)}")
        self.shape = shape
        super().__init__(**kwargs)

    # Upstream _setup calls self.add_tee(...); overriding it swaps the block
    # (and with it the goal silhouette + coverage geometry) in one place.
    def add_tee(self, space, position, angle, scale=30, color="LightSlateGray", mask=None):
        return _add_block(space, position, angle, SHAPES[self.shape], color)


gym.register(id=ENV_ID, entry_point=PushShapeEnv, max_episode_steps=300)
