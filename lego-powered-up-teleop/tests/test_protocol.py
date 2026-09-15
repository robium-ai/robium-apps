from __future__ import annotations

import pytest

from lego_powered_up_teleop.protocol import LineDecoder, decode_drive, encode_drive, mix


def test_drive_packet_round_trip() -> None:
    for powers in ((0, 0), (35, 35), (-35, 35), (-100, 100)):
        assert decode_drive(encode_drive(*powers)) == powers


def test_drive_packet_rejects_out_of_range_power() -> None:
    with pytest.raises(ValueError):
        encode_drive(101, 0)


def test_drive_packet_rejects_non_integer_power() -> None:
    with pytest.raises(TypeError):
        encode_drive(20.5, 0)  # type: ignore[arg-type]


def test_mix_cardinal_directions() -> None:
    assert mix(1, 0, 35) == (35, 35)
    assert mix(-1, 0, 35) == (-35, -35)
    assert mix(0, -1, 35) == (-35, 35)
    assert mix(0, 1, 35) == (35, -35)


def test_mix_preserves_curve_when_inputs_overflow() -> None:
    left, right = mix(1, 0.5, 40)
    assert left == 40
    assert 0 < right < left


def test_line_decoder_reassembles_chunks_and_multiple_lines() -> None:
    decoder = LineDecoder()
    assert decoder.feed(b"REA") == []
    assert decoder.feed(b"DY\nPONG\npar") == ["READY", "PONG"]
    assert decoder.feed(b"tial\n") == ["partial"]
