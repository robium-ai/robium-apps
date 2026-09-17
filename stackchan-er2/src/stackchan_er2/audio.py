"""Small replaceable TTS adapters."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

from .config import SAMPLE_RATE


class MacSayTTS:
    """Render the built-in macOS voice to mono signed 16-bit PCM."""

    def __init__(self, voice: str | None = None):
        self.voice = voice

    @staticmethod
    def doctor() -> list[str]:
        missing = [name for name in ("say", "afconvert") if shutil.which(name) is None]
        return missing

    def synthesize(self, text: str) -> bytes:
        with tempfile.TemporaryDirectory(prefix="stackchan-tts-") as directory:
            aiff = Path(directory) / "speech.aiff"
            wav_path = Path(directory) / "speech.wav"
            say_command = ["say", "-o", str(aiff)]
            if self.voice:
                say_command[1:1] = ["-v", self.voice]
            say_command.append(text)
            subprocess.run(say_command, check=True, capture_output=True)
            subprocess.run(
                [
                    "afconvert",
                    "-f",
                    "WAVE",
                    "-d",
                    f"LEI16@{SAMPLE_RATE}",
                    "-c",
                    "1",
                    str(aiff),
                    str(wav_path),
                ],
                check=True,
                capture_output=True,
            )
            with wave.open(str(wav_path), "rb") as wav_file:
                if (
                    wav_file.getnchannels() != 1
                    or wav_file.getsampwidth() != 2
                    or wav_file.getframerate() != SAMPLE_RATE
                ):
                    raise RuntimeError("macOS TTS conversion produced an unexpected audio format")
                return wav_file.readframes(wav_file.getnframes())


class FakeTTS:
    def synthesize(self, text: str) -> bytes:
        sample_count = max(1, min(SAMPLE_RATE, len(text) * 200))
        return b"\0\0" * sample_count
