from collections import defaultdict

import pygame

from lego_stackchan_drive.core import Controls
from lego_stackchan_drive.main import operator_input
from lego_stackchan_drive.vendor.gamepad import GamepadReading


def test_background_gamepad_ignores_keyboard_focus_and_stale_keys():
    keys = defaultdict(bool, {pygame.K_UP: True, pygame.K_SPACE: True})
    action, source = operator_input(
        GamepadReading(throttle=.8, steer=-.4), keys,
        focused=False, controller_connected=True,
    )
    assert action == (.8, -.4) and source == 'gamepad'


def test_background_keyboard_cannot_drive_robot():
    keys = defaultdict(bool, {pygame.K_UP: True, pygame.K_RIGHT: True})
    action, _ = operator_input(
        GamepadReading(), keys, focused=False, controller_connected=False,
    )
    assert action == (0, 0)


def test_background_gamepad_drives_without_arming():
    keys = defaultdict(bool)
    control = Controls()
    for reading, expected in ((GamepadReading(), (0, 0)),
                              (GamepadReading(throttle=1), (75, 75))):
        requested, _ = operator_input(
            reading, keys, focused=False, controller_connected=True,
        )
        import time
        control.camera_tick(time.monotonic())
        control.update(requested, True)
        assert control.command()[1] == expected
    assert not hasattr(control, 'armed')


def test_keyboard_space_does_not_stop_driving():
    keys = defaultdict(bool, {pygame.K_UP: True, pygame.K_SPACE: True})
    requested, source = operator_input(
        GamepadReading(), keys, focused=True, controller_connected=False,
    )
    assert requested == (1, 0) and source == 'keyboard'
    keys[pygame.K_SPACE] = False
    assert operator_input(GamepadReading(), keys, focused=True, controller_connected=False)[0] == (1, 0)
