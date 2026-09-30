import numpy as np
import pytest

from lego_stackchan_drive.speech import RATE, pcm16


def test_pcm_signed_endpoints_padding_and_duration():
    audio = np.frombuffer(pcm16(np.array([-2, -1, 0, 1, 2]), RATE), dtype="<i2")
    assert audio[:4800].tolist() == [0] * 4800
    assert audio[4800:4805].tolist() == [-32768, -32768, 0, 32767, 32767]
    assert len(audio) == 12005
    assert not audio[-7200:].any()


@pytest.mark.parametrize("samples, rate", [
    ([], RATE), ([np.nan], RATE), ([np.inf], RATE), ([[0, 1]], RATE),
    ([0, 1], 16000), (np.zeros(468001), RATE),
])
def test_invalid_generated_audio_never_reaches_board(samples, rate):
    with pytest.raises(ValueError):
        pcm16(samples, rate)
