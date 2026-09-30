import math

import pytest
from test_controls import Pad

from lego_stackchan_drive.policy import HoldToModel, bounded_action
from lego_stackchan_drive.vendor.gamepad import read_gamepad


def choose(hold, manual=(0, 0), **changes):
    options = {'held': True, 'connected': True, 'available': True, 'now': 100,
               'frame': {'sequence': 20, 'stream_generation': 1},
               'prediction': {'sequence': 20, 'stream_generation': 1,
                              'capture_t': 99.95, 'raw_action': [1.02, -.8]}}
    options.update(changes)
    return hold.choose(manual, **options)


def test_hold_runs_model_and_release_and_manual_takeover_are_immediate():
    h = HoldToModel()
    assert choose(h) == ((1, -.8), 'model')
    assert choose(h, held=False) == ((0, 0), 'manual')
    assert choose(h) == ((1, -.8), 'model')
    assert choose(h, (.5, .2)) == ((.5, .2), 'manual override')
    assert choose(h, (-1, 0), available=False) == ((-1, 0), 'manual override')
    assert choose(h, (.6, 0), held=False) == ((.6, 0), 'manual')
    assert not hasattr(h, 'armed')


@pytest.mark.parametrize('changes', [
    {'connected': False}, {'available': False}, {'prediction': None}, {'frame': None},
    {'prediction': {'capture_t': 99.5, 'sequence': 20, 'stream_generation': 1, 'raw_action': [1, 0]}},
    {'prediction': {'capture_t': 100.1, 'sequence': 20, 'stream_generation': 1, 'raw_action': [1, 0]}},
    {'prediction': {'capture_t': 99.95, 'sequence': 21, 'stream_generation': 1, 'raw_action': [1, 0]}},
    {'prediction': {'capture_t': 99.95, 'sequence': 20, 'stream_generation': 0, 'raw_action': [1, 0]}},
    {'prediction': {'capture_t': 99.95, 'sequence': 20, 'stream_generation': 1, 'raw_action': [math.nan, 0]}},
])
def test_missing_controller_stale_wrong_stream_or_invalid_prediction_cannot_drive(changes):
    assert choose(HoldToModel(), **changes)[0] == (0, 0)


def test_trial_limit_does_not_block_manual_and_release_begins_new_hold():
    h = HoldToModel(20)
    assert choose(h)[1] == 'model'
    assert choose(h, now=120)[1].startswith('trial complete')
    assert choose(h, (1, 0), now=120)[0] == (1, 0)
    choose(h, held=False, now=120)
    prediction = {'sequence': 20, 'stream_generation': 1, 'capture_t': 120, 'raw_action': [1, -.8]}
    assert choose(h, now=120.05, prediction=prediction)[1] == 'model'


def test_camera_latency_and_two_dropped_frames_do_not_pulse_motor_commands():
    h = HoldToModel()
    # Measured ~210 ms acquisition/encoding/inference age, followed by the
    # next 100 ms camera interval. Missing two frames adds another 200 ms.
    prediction = {'sequence': 20, 'stream_generation': 1,
                  'capture_t': 99.8, 'raw_action': [1, -.4]}
    for now in (100.01, 100.09, 100.19, 100.29):
        assert choose(h, now=now, prediction=prediction) == ((1, -.4), 'model')
    assert choose(h, now=100.3, prediction=prediction)[0] == (0, 0)
    assert choose(h, (.3, 0), now=100.3, prediction=prediction)[0] == (.3, 0)
    assert choose(h, now=100.09, prediction=prediction, held=False)[0] == (0, 0)


def test_nonfinite_actions_rejected_and_range_clamped():
    assert bounded_action([1.02, -1.04]) == (1, -1)
    for invalid in ([1], [float('inf'), 0], [0, float('nan')]):
        with pytest.raises(ValueError):
            bounded_action(invalid)


def test_model_hold_does_not_affect_axes_or_recording_triggers():
    reading = read_gamepad(Pad([0, -1, .5, 0, 1, -1]), policy_held=True)
    assert reading.policy_held and reading.record_held
    assert reading.throttle == 1 and reading.steer > 0


def test_laptop_space_drives_without_gamepad_and_release_or_focus_loss_stops():
    from collections import defaultdict

    import pygame

    from lego_stackchan_drive.main import model_input
    from lego_stackchan_drive.vendor.gamepad import GamepadReading

    keys = defaultdict(bool, {pygame.K_SPACE: True})
    hold = HoldToModel()

    def keyboard_choose(*, focused=True, manual=(0, 0), **changes):
        held, connected = model_input(GamepadReading(), keys, focused=focused,
                                      controller_connected=False)
        return choose(hold, manual, held=held, connected=connected, **changes)

    assert keyboard_choose()[1] == 'model'
    assert keyboard_choose(focused=False) == ((0, 0), 'manual')
    assert keyboard_choose()[1] == 'model'
    keys[pygame.K_SPACE] = False
    assert keyboard_choose() == ((0, 0), 'manual')
    keys[pygame.K_SPACE] = True
    assert keyboard_choose(manual=(.5, 0)) == ((.5, 0), 'manual override')
    assert keyboard_choose(available=False)[0] == (0, 0)
    assert keyboard_choose(now=120)[1].startswith('trial complete')


def test_r1_still_works_in_background_but_disconnected_r1_is_ignored():
    from collections import defaultdict

    from lego_stackchan_drive.main import model_input
    from lego_stackchan_drive.vendor.gamepad import GamepadReading

    reading = GamepadReading(policy_held=True)
    assert model_input(reading, defaultdict(bool), focused=False,
                       controller_connected=True) == (True, True)
    assert model_input(reading, defaultdict(bool), focused=False,
                       controller_connected=False) == (False, False)
