"""Pygame gamepad discovery and normalized differential-drive input."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

import pygame

DEFAULT_STEER_AXIS = 2
DEFAULT_THROTTLE_AXIS = 1
DEFAULT_DEADZONE = 0.10
DEFAULT_STOP_BUTTON = 0
SDL_DPAD_UP_BUTTON = 11
SDL_DPAD_DOWN_BUTTON = 12
SDL_DPAD_LEFT_BUTTON = 13
SDL_DPAD_RIGHT_BUTTON = 14


class JoystickLike(Protocol):
    def get_instance_id(self) -> int: ...

    def get_name(self) -> str: ...

    def get_numaxes(self) -> int: ...

    def get_axis(self, axis: int) -> float: ...

    def get_numbuttons(self) -> int: ...

    def get_button(self, button: int) -> bool: ...

    def get_numhats(self) -> int: ...

    def get_hat(self, hat: int) -> tuple[int, int]: ...


@dataclass(frozen=True)
class GamepadReading:
    throttle: float = 0.0
    steer: float = 0.0
    stop: bool = False


def apply_deadzone(value: float, deadzone: float) -> float:
    """Remove center noise and rescale the remaining axis to the full range."""
    if not 0.0 <= deadzone < 1.0:
        raise ValueError("deadzone must be at least 0 and less than 1")
    value = max(-1.0, min(1.0, float(value)))
    magnitude = abs(value)
    if magnitude <= deadzone:
        return 0.0
    return math.copysign((magnitude - deadzone) / (1.0 - deadzone), value)


def read_gamepad(
    joystick: JoystickLike,
    *,
    steer_axis: int = DEFAULT_STEER_AXIS,
    throttle_axis: int = DEFAULT_THROTTLE_AXIS,
    deadzone: float = DEFAULT_DEADZONE,
    stop_button: int = DEFAULT_STOP_BUTTON,
) -> GamepadReading:
    """Read left-stick throttle and right-stick steering, with D-pad fallback."""
    stop = (
        0 <= stop_button < joystick.get_numbuttons()
        and bool(joystick.get_button(stop_button))
    )
    if stop:
        return GamepadReading(stop=True)

    steer = (
        apply_deadzone(joystick.get_axis(steer_axis), deadzone)
        if 0 <= steer_axis < joystick.get_numaxes()
        else 0.0
    )
    # SDL reports stick-up as negative; the robot API defines forward as positive.
    throttle = (
        apply_deadzone(-joystick.get_axis(throttle_axis), deadzone)
        if 0 <= throttle_axis < joystick.get_numaxes()
        else 0.0
    )

    if throttle == 0.0 and steer == 0.0:
        if joystick.get_numhats() > 0:
            hat_x, hat_y = joystick.get_hat(0)
            steer = float(hat_x)
            throttle = float(hat_y)
        elif joystick.get_numbuttons() > SDL_DPAD_RIGHT_BUTTON:
            steer = float(joystick.get_button(SDL_DPAD_RIGHT_BUTTON)) - float(
                joystick.get_button(SDL_DPAD_LEFT_BUTTON)
            )
            throttle = float(joystick.get_button(SDL_DPAD_UP_BUTTON)) - float(
                joystick.get_button(SDL_DPAD_DOWN_BUTTON)
            )
    return GamepadReading(throttle=throttle, steer=steer)


class GamepadManager:
    """Track hot-plugged Pygame controllers and expose one active reading."""

    def __init__(
        self,
        *,
        steer_axis: int = DEFAULT_STEER_AXIS,
        throttle_axis: int = DEFAULT_THROTTLE_AXIS,
        deadzone: float = DEFAULT_DEADZONE,
        stop_button: int = DEFAULT_STOP_BUTTON,
    ) -> None:
        self.steer_axis = steer_axis
        self.throttle_axis = throttle_axis
        self.deadzone = deadzone
        self.stop_button = stop_button
        self._joysticks: dict[int, JoystickLike] = {}
        pygame.joystick.init()
        for device_index in range(pygame.joystick.get_count()):
            self.add(device_index)

    def add(self, device_index: int) -> None:
        joystick = pygame.joystick.Joystick(device_index)
        self._joysticks[joystick.get_instance_id()] = joystick

    def remove(self, instance_id: int) -> None:
        self._joysticks.pop(instance_id, None)

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.JOYDEVICEADDED:
            self.add(event.device_index)
        elif event.type == pygame.JOYDEVICEREMOVED:
            self.remove(event.instance_id)

    @property
    def active(self) -> JoystickLike | None:
        return next(iter(self._joysticks.values()), None)

    @property
    def label(self) -> str:
        active = self.active
        return active.get_name() if active is not None else "not connected"

    def read(self) -> GamepadReading:
        active = self.active
        if active is None:
            return GamepadReading()
        try:
            return read_gamepad(
                active,
                steer_axis=self.steer_axis,
                throttle_axis=self.throttle_axis,
                deadzone=self.deadzone,
                stop_button=self.stop_button,
            )
        except pygame.error:
            self.remove(active.get_instance_id())
            return GamepadReading()
