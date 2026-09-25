import numpy as np
import pytest

from stackchan_er2_sim.speech import mono_16k


def test_audio_is_resampled_to_16khz() -> None:
    source = np.linspace(-0.5, 0.5, 48_000, dtype="<f4")
    output = mono_16k(source.tobytes(), 48_000)
    assert len(output) == 16_000
    assert output.dtype == np.float32


def test_audio_rejects_malformed_pcm() -> None:
    with pytest.raises(ValueError):
        mono_16k(b"123", 16_000)
