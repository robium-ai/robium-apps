"""Lazy local Whisper and Kokoro adapters."""

from __future__ import annotations

import io
import threading
from typing import Any

import numpy as np
import soundfile as sf

from .config import KOKORO_MODEL, KOKORO_VOICES, SAMPLE_RATE, WHISPER_MODEL


def mono_16k(pcm: bytes, sample_rate: int) -> np.ndarray:
    if sample_rate < 8_000 or sample_rate > 96_000:
        raise ValueError("sample_rate must be between 8000 and 96000")
    if not pcm or len(pcm) % 4:
        raise ValueError("audio must be non-empty little-endian float32 PCM")
    audio = np.frombuffer(pcm, dtype="<f4").astype(np.float32)
    if sample_rate == SAMPLE_RATE:
        return np.clip(audio, -1.0, 1.0)
    output_count = max(1, round(len(audio) * SAMPLE_RATE / sample_rate))
    source_x = np.linspace(0.0, 1.0, len(audio), endpoint=False)
    output_x = np.linspace(0.0, 1.0, output_count, endpoint=False)
    return np.interp(output_x, source_x, audio).astype(np.float32)


class LocalSpeech:
    def __init__(self, *, voice: str = "am_puck", speed: float = 1.03):
        self.voice = voice
        self.speed = speed
        self._whisper: Any = None
        self._kokoro: Any = None
        self._whisper_lock = threading.Lock()
        self._kokoro_lock = threading.Lock()

    def status(self) -> dict[str, Any]:
        return {
            "stt": "ready" if WHISPER_MODEL.is_file() else "missing",
            "tts": "ready" if KOKORO_MODEL.is_file() and KOKORO_VOICES.is_file() else "missing",
            "stt_model": "Whisper base.en Q5_1",
            "tts_model": "Kokoro-82M v1.0 int8",
            "voice": self.voice,
        }

    def _load_whisper(self) -> Any:
        if not WHISPER_MODEL.is_file():
            raise RuntimeError("Whisper model is missing; run ./app build")
        if self._whisper is None:
            from pywhispercpp.model import Model

            self._whisper = Model(
                str(WHISPER_MODEL),
                print_realtime=False,
                print_progress=False,
                print_timestamps=False,
            )
        return self._whisper

    def _load_kokoro(self) -> Any:
        if not KOKORO_MODEL.is_file() or not KOKORO_VOICES.is_file():
            raise RuntimeError("Kokoro model is missing; run ./app build")
        if self._kokoro is None:
            from kokoro_onnx import Kokoro

            self._kokoro = Kokoro(str(KOKORO_MODEL), str(KOKORO_VOICES))
        return self._kokoro

    def transcribe(self, pcm: bytes, sample_rate: int) -> str:
        audio = mono_16k(pcm, sample_rate)
        with self._whisper_lock:
            segments = self._load_whisper().transcribe(audio)
        return " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()

    def synthesize(self, text: str) -> bytes:
        text = text.strip()
        if not text:
            raise ValueError("speech text must be non-empty")
        with self._kokoro_lock:
            samples, sample_rate = self._load_kokoro().create(
                text,
                voice=self.voice,
                speed=self.speed,
                lang="en-us",
            )
        output = io.BytesIO()
        sf.write(output, samples, sample_rate, format="WAV", subtype="PCM_16")
        return output.getvalue()
