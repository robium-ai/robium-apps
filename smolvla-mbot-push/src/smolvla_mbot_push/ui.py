"""Window and control input.

Both live here, and both are pygame, deliberately. OpenCV bundles its own copy
of SDL2 and pygame bundles another; loading both makes macOS warn about
duplicate Objective-C classes and risks genuine crashes. Since pygame already
does everything the preview needed - a window, a scale, some text - dropping
OpenCV removes the conflict rather than papering over it.
"""

from __future__ import annotations

import os

import numpy as np

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame  # noqa: E402

# How fast a held key ramps toward full deflection, in units per second.
# Instant full throttle would make every keyboard demonstration a square wave,
# which is poor material to clone; this gives something closer to a stick.
KEY_RAMP_PER_S = 3.0
KEY_RELEASE_PER_S = 6.0

STICK_DEADZONE = 0.12
DEFAULT_THROTTLE_AXIS = 1
DEFAULT_STEER_AXIS = 2


class Viewer:
    """A window showing the overhead frame."""

    def __init__(self, size: int = 640, title: str = "overhead"):
        pygame.init()
        pygame.display.set_caption(title)
        self._screen = pygame.display.set_mode((size, size))
        # The built-in font, not SysFont: a system-font lookup shells out to
        # fc-list, which is absent on stock macOS and times out slowly before
        # falling back to this same font anyway.
        self._font = pygame.font.Font(None, 22)
        self.size = size

    def show(self, frame: np.ndarray, lines: list[str]) -> None:
        """Draw one RGB frame, scaled to the window, with a text overlay."""
        # pygame wants (width, height, 3); the renderer gives (height, width, 3).
        surface = pygame.surfarray.make_surface(frame.swapaxes(0, 1))
        surface = pygame.transform.smoothscale(surface, (self.size, self.size))
        self._screen.blit(surface, (0, 0))

        for index, line in enumerate(lines):
            # Draw twice, offset, so the text stays readable on a white arena.
            text = self._font.render(line, True, (255, 255, 255))
            self._screen.blit(text, (11, 11 + index * 20))
            text = self._font.render(line, True, (20, 20, 20))
            self._screen.blit(text, (10, 10 + index * 20))

        pygame.display.flip()

    def close(self) -> None:
        pygame.display.quit()


class Teleop:
    """Reads a normalized (throttle, steer) action.

    Uses a game controller when one is attached and falls back to the keyboard
    otherwise, so the arena is drivable with nothing plugged in.
    """

    def __init__(self, throttle_axis: int = DEFAULT_THROTTLE_AXIS, steer_axis: int = DEFAULT_STEER_AXIS):
        pygame.init()
        pygame.joystick.init()
        self._stick = None
        if pygame.joystick.get_count() > 0:
            self._stick = pygame.joystick.Joystick(0)
            self._stick.init()
            self.source = f"gamepad: {self._stick.get_name()}"
        else:
            self.source = "keyboard: arrows or WASD"
        self._throttle_axis = throttle_axis
        self._steer_axis = steer_axis
        self._action = np.zeros(2, dtype=float)

    @property
    def using_gamepad(self) -> bool:
        return self._stick is not None

    def read(self, dt: float) -> np.ndarray:
        """Current action as (throttle, steer), each in [-1, 1]."""
        if self._stick is not None:
            # Forward on a stick reads negative; flip so positive is forward.
            self._action = np.array(
                [-self._axis(self._throttle_axis), self._axis(self._steer_axis)]
            )
            return self._action
        return self._from_keyboard(dt)

    def _axis(self, axis: int) -> float:
        if axis >= self._stick.get_numaxes():
            return 0.0
        value = float(self._stick.get_axis(axis))
        if abs(value) < STICK_DEADZONE:
            return 0.0
        # Rescale so motion starts smoothly at the dead-zone edge rather than
        # jumping straight to the dead-zone magnitude.
        span = (abs(value) - STICK_DEADZONE) / (1.0 - STICK_DEADZONE)
        return float(np.sign(value) * span)

    def _from_keyboard(self, dt: float) -> np.ndarray:
        keys = pygame.key.get_pressed()
        target = np.array(
            [
                float(keys[pygame.K_UP] or keys[pygame.K_w])
                - float(keys[pygame.K_DOWN] or keys[pygame.K_s]),
                float(keys[pygame.K_RIGHT] or keys[pygame.K_d])
                - float(keys[pygame.K_LEFT] or keys[pygame.K_a]),
            ]
        )
        for i in (0, 1):
            rate = KEY_RAMP_PER_S if target[i] != 0.0 else KEY_RELEASE_PER_S
            step = rate * dt
            delta = target[i] - self._action[i]
            self._action[i] += float(np.clip(delta, -step, step))
        return self._action.copy()

    def close(self) -> None:
        pygame.joystick.quit()
