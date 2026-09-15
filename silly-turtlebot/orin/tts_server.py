#!/usr/bin/env python3
"""Local neural TTS service for the Orin-connected robot speaker."""

from __future__ import annotations

import io
import json
import os
import re
import subprocess
import threading
import time
import wave
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import soundfile as sf
from kokoro_onnx import Kokoro


MAX_REQUEST_BYTES = 16 * 1024
MAX_SPEECH_CHARS = 240
USB_DEVICE = re.compile(r"card (\d+):.*(?:USB|Speaker).*device (\d+):", re.I)


class SpeechBusy(RuntimeError):
    """Raised when another line is already being synthesized or played."""


def pad_pcm16_wav(
    wav_bytes: bytes,
    leading_silence_ms: int,
    trailing_silence_ms: int,
) -> bytes:
    """Add PCM silence so a sleeping USB speaker cannot eat speech phonemes."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as source:
        params = source.getparams()
        frames = source.readframes(params.nframes)
    if params.sampwidth != 2:
        raise ValueError("TTS pre-roll requires PCM 16-bit audio")
    frame_width = params.nchannels * params.sampwidth
    leading_frames = round(params.framerate * leading_silence_ms / 1000)
    trailing_frames = round(params.framerate * trailing_silence_ms / 1000)
    padded = io.BytesIO()
    with wave.open(padded, "wb") as target:
        target.setparams(params)
        target.writeframes(
            b"\x00" * (leading_frames * frame_width)
            + frames
            + b"\x00" * (trailing_frames * frame_width)
        )
    return padded.getvalue()


class SpeechState:
    def __init__(self) -> None:
        self.model_path = os.environ.get(
            "KOKORO_MODEL", "/models/kokoro-v1.0.int8.onnx"
        )
        self.voices_path = os.environ.get(
            "KOKORO_VOICES", "/models/voices-v1.0.bin"
        )
        self.voice_name = os.environ.get("KOKORO_VOICE", "am_puck")
        self.speed = float(os.environ.get("KOKORO_SPEED", "1.03"))
        self.configured_audio_device = os.environ.get("TTS_AUDIO_DEVICE", "auto")
        self.leading_silence_ms = int(os.environ.get("TTS_LEADING_SILENCE_MS", "500"))
        self.trailing_silence_ms = int(os.environ.get("TTS_TRAILING_SILENCE_MS", "100"))
        if not 0 <= self.leading_silence_ms <= 2000:
            raise ValueError("TTS_LEADING_SILENCE_MS must be between 0 and 2000")
        if not 0 <= self.trailing_silence_ms <= 2000:
            raise ValueError("TTS_TRAILING_SILENCE_MS must be between 0 and 2000")
        self._speech_lock = threading.Lock()
        started = time.monotonic()
        self.voice = Kokoro(self.model_path, self.voices_path)
        self.load_time_s = round(time.monotonic() - started, 3)

    def audio_device(self) -> str | None:
        if self.configured_audio_device != "auto":
            return self.configured_audio_device
        completed = subprocess.run(
            ["aplay", "-l"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5.0,
        )
        for line in completed.stdout.splitlines():
            match = USB_DEVICE.search(line)
            if match:
                return f"plughw:{match.group(1)},{match.group(2)}"
        return None

    def health(self) -> dict[str, Any]:
        device = self.audio_device()
        return {
            "status": "ok" if device is not None else "waiting_for_speaker",
            "model": "Kokoro-82M-v1.0-int8",
            "voice": self.voice_name,
            "speed": self.speed,
            "audio_device": device,
            "load_time_s": self.load_time_s,
            "leading_silence_ms": self.leading_silence_ms,
            "trailing_silence_ms": self.trailing_silence_ms,
        }

    def speak(self, text: str) -> dict[str, Any]:
        text = text.strip()
        if not text:
            raise ValueError("speech must be non-empty")
        if len(text) > MAX_SPEECH_CHARS:
            raise ValueError(f"speech exceeds {MAX_SPEECH_CHARS} characters")
        if not self._speech_lock.acquire(blocking=False):
            raise SpeechBusy("another line is already playing")
        started = time.monotonic()
        try:
            samples, sample_rate = self.voice.create(
                text,
                voice=self.voice_name,
                speed=self.speed,
                lang="en-us",
            )
            wav = io.BytesIO()
            sf.write(wav, samples, sample_rate, format="WAV", subtype="PCM_16")
            audio = pad_pcm16_wav(
                wav.getvalue(),
                self.leading_silence_ms,
                self.trailing_silence_ms,
            )
            device = self.audio_device()
            if device is None:
                raise RuntimeError(
                    "no USB speaker detected; connect one or set TTS_AUDIO_DEVICE"
                )
            completed = subprocess.run(
                ["aplay", "-q", "-D", device],
                input=audio,
                check=False,
                capture_output=True,
                timeout=30.0,
            )
            if completed.returncode:
                reason = completed.stderr.decode("utf-8", errors="replace").strip()
                raise RuntimeError(reason or "audio playback failed")
            return {
                "status": "succeeded",
                "message": text,
                "model": "Kokoro-82M-v1.0-int8",
                "voice": self.voice_name,
                "audio_device": device,
                "leading_silence_ms": self.leading_silence_ms,
                "trailing_silence_ms": self.trailing_silence_ms,
                "elapsed_s": round(time.monotonic() - started, 3),
            }
        finally:
            self._speech_lock.release()


def make_handler(state: SpeechState):
    class Handler(BaseHTTPRequestHandler):
        def _write_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json_body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_REQUEST_BYTES:
                raise ValueError("request body size is invalid")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("request body must be a JSON object")
            return payload

        def do_GET(self) -> None:
            if self.path == "/health":
                self._write_json(HTTPStatus.OK, state.health())
                return
            self._write_json(HTTPStatus.NOT_FOUND, {"status": "not_found"})

        def do_POST(self) -> None:
            if self.path != "/speak":
                self._write_json(HTTPStatus.NOT_FOUND, {"status": "not_found"})
                return
            try:
                payload = state.speak(str(self._json_body().get("message", "")))
                self._write_json(HTTPStatus.OK, payload)
            except (ValueError, TypeError, json.JSONDecodeError) as error:
                self._write_json(
                    HTTPStatus.BAD_REQUEST,
                    {"status": "rejected", "reason": str(error)},
                )
            except SpeechBusy as error:
                self._write_json(
                    HTTPStatus.CONFLICT,
                    {"status": "busy", "reason": str(error)},
                )
            except Exception as error:  # noqa: BLE001 - service failure boundary.
                self._write_json(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {"status": "failed", "reason": str(error)},
                )

        def log_message(self, _format: str, *_args: Any) -> None:
            return

    return Handler


def main() -> None:
    state = SpeechState()
    server = ThreadingHTTPServer(("0.0.0.0", 8082), make_handler(state))
    print(
        "Kokoro TTS ready on http://0.0.0.0:8082; "
        f"voice={state.voice_name}; audio={state.audio_device() or 'waiting'}",
        flush=True,
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
