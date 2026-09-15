from __future__ import annotations

import os

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from lego_powered_up_teleop.gamepad import GamepadManager, apply_deadzone, read_gamepad


class FakeJoystick:
    def __init__(
        self,
        *,
        axes: tuple[float, ...] = (0.0, 0.0, 0.0),
        buttons: tuple[bool, ...] = (False,),
        hats: tuple[tuple[int, int], ...] = (),
    ) -> None:
        self.axes = axes
        self.buttons = buttons
        self.hats = hats

    def get_instance_id(self) -> int:
        return 7

    def get_name(self) -> str:
        return "Stadia Controller"

    def get_numaxes(self) -> int:
        return len(self.axes)

    def get_axis(self, axis: int) -> float:
        return self.axes[axis]

    def get_numbuttons(self) -> int:
        return len(self.buttons)

    def get_button(self, button: int) -> bool:
        return self.buttons[button]

    def get_numhats(self) -> int:
        return len(self.hats)

    def get_hat(self, hat: int) -> tuple[int, int]:
        return self.hats[hat]


def test_deadzone_removes_noise_and_preserves_full_scale() -> None:
    assert apply_deadzone(0.08, 0.10) == 0.0
    assert apply_deadzone(-0.08, 0.10) == 0.0
    assert apply_deadzone(1.0, 0.10) == 1.0
    assert apply_deadzone(-1.0, 0.10) == -1.0


def test_deadzone_rescales_remaining_travel() -> None:
    assert apply_deadzone(0.55, 0.10) == pytest.approx(0.5)


def test_stadia_split_sticks_map_left_up_and_right_right() -> None:
    reading = read_gamepad(FakeJoystick(axes=(0.0, -1.0, 0.55)), deadzone=0.10)
    assert reading.throttle == 1.0
    assert reading.steer == pytest.approx(0.5)
    assert not reading.stop


def test_dpad_is_fallback_when_left_stick_is_centered() -> None:
    reading = read_gamepad(FakeJoystick(hats=((-1, 1),)))
    assert (reading.throttle, reading.steer) == (1.0, -1.0)


def test_stadia_button_dpad_is_supported_when_sdl_reports_no_hat() -> None:
    buttons = [False] * 17
    buttons[11] = True
    buttons[14] = True
    reading = read_gamepad(FakeJoystick(buttons=tuple(buttons)))
    assert (reading.throttle, reading.steer) == (1.0, 1.0)


def test_analog_stick_takes_priority_over_dpad() -> None:
    reading = read_gamepad(FakeJoystick(axes=(0.0, -1.0, 0.0), hats=((-1, 0),)))
    assert (reading.throttle, reading.steer) == (1.0, 0.0)


def test_a_button_is_an_immediate_stop() -> None:
    reading = read_gamepad(FakeJoystick(axes=(0.0, -1.0, 1.0), buttons=(True,)))
    assert (reading.throttle, reading.steer, reading.stop) == (0.0, 0.0, True)


def test_missing_axes_fail_stopped() -> None:
    reading = read_gamepad(FakeJoystick(axes=(), buttons=(), hats=()))
    assert (reading.throttle, reading.steer, reading.stop) == (0.0, 0.0, False)


def test_deadzone_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        apply_deadzone(0.0, 1.0)


def test_hotplug_removal_immediately_returns_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    joystick = FakeJoystick(axes=(0.0, -1.0, 1.0))
    monkeypatch.setattr(pygame.joystick, "get_count", lambda: 1)
    monkeypatch.setattr(pygame.joystick, "Joystick", lambda _index: joystick)
    manager = GamepadManager()
    assert manager.read().throttle == 1.0

    event = pygame.event.Event(pygame.JOYDEVICEREMOVED, instance_id=7)
    manager.handle_event(event)

    assert manager.active is None
    assert manager.read().throttle == 0.0
