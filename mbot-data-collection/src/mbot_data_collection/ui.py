"""Window and control input.

Both are pygame, deliberately: it draws the preview and reads the gamepad, so
the process never loads a second SDL alongside OpenCV's.

The keyboard path ramps instead of switching. Holding an arrow key would
otherwise produce a square wave, and square waves are poor material to clone -
the recorded action would jump from 0 to full in one tick, which no policy can
reproduce smoothly and no chassis can actually follow.
"""

from __future__ import annotations

import os

import numpy as np

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame  # noqa: E402

KEY_RAMP_PER_S = 2.5
KEY_RELEASE_PER_S = 5.0

DEFAULT_STICK_DEADZONE = 0.12
DEFAULT_THROTTLE_AXIS = 1  # left stick, vertical
DEFAULT_STEER_AXIS = 2  # right stick, horizontal


class Viewer:
    """A window showing the webcam frame with a text overlay."""

    def __init__(self, width: int = 720, title: str = "mbot"):
        pygame.init()
        pygame.display.set_caption(title)
        self._width = width
        self._screen: pygame.Surface | None = None
        # The built-in font, not SysFont: a system-font lookup shells out to
        # fc-list, which is absent on stock macOS and times out slowly before
        # falling back to this same font anyway.
        self._font = pygame.font.Font(None, 24)

    def _ensure(self, frame: np.ndarray) -> tuple[int, int]:
        height, width = frame.shape[:2]
        size = (self._width, int(round(self._width * height / width)))
        if self._screen is None or self._screen.get_size() != size:
            self._screen = pygame.display.set_mode(size)
        return size

    def show(self, frame: np.ndarray, lines: list[str]) -> None:
        size = self._ensure(frame)
        assert self._screen is not None
        # pygame wants (width, height, 3); a camera frame is (height, width, 3).
        surface = pygame.surfarray.make_surface(frame.swapaxes(0, 1))
        self._screen.blit(pygame.transform.smoothscale(surface, size), (0, 0))

        for index, line in enumerate(lines):
            # Drawn twice, offset, so text stays readable over any scene.
            for colour, offset in (((0, 0, 0), 1), ((255, 255, 255), 0)):
                text = self._font.render(line, True, colour)
                self._screen.blit(text, (11 + offset, 11 + offset + index * 22))
        pygame.display.flip()

    def close(self) -> None:
        pygame.display.quit()


class Teleop:
    """Reads a normalized (throttle, steer) action from a gamepad or the keys."""

    def __init__(
        self,
        throttle_axis: int = DEFAULT_THROTTLE_AXIS,
        steer_axis: int = DEFAULT_STEER_AXIS,
        prefer_keyboard: bool = False,
        deadzone: float = DEFAULT_STICK_DEADZONE,
    ):
        pygame.init()
        pygame.joystick.init()
        self._stick = None
        if not prefer_keyboard and pygame.joystick.get_count() > 0:
            self._stick = pygame.joystick.Joystick(0)
            self._stick.init()
            self.source = f"gamepad: {self._stick.get_name()}"
        else:
            self.source = "keyboard: arrows or WASD"
        self._throttle_axis = throttle_axis
        self._steer_axis = steer_axis
        self._deadzone = float(np.clip(deadzone, 0.0, 0.9))
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
            return self._action.copy()
        return self._from_keyboard(dt)

    def _axis(self, axis: int) -> float:
        assert self._stick is not None
        if axis >= self._stick.get_numaxes():
            return 0.0
        value = float(self._stick.get_axis(axis))
        if abs(value) < self._deadzone:
            return 0.0
        # Rescale so motion starts smoothly at the dead-zone edge rather than
        # jumping straight to the dead-zone magnitude.
        span = (abs(value) - self._deadzone) / (1.0 - self._deadzone)
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

    def reset(self) -> None:
        """Drop to neutral, ramp included, so a stop key really stops."""
        self._action[:] = 0.0

    def close(self) -> None:
        pygame.joystick.quit()
