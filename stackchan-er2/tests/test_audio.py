from __future__ import annotations

from stackchan_er2.audio import FakeTTS, MacSayTTS


def test_fake_tts_returns_even_pcm() -> None:
    pcm = FakeTTS().synthesize("hello")
    assert pcm
    assert len(pcm) % 2 == 0


def test_macos_tts_dependencies_exist_on_target_host() -> None:
    assert MacSayTTS.doctor() == []
