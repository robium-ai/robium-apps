from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCAL = ROOT / ".local"
MODEL_DIR = LOCAL / "models"
SIM_SOURCE = LOCAL / "stackchan-simulator"
SIM_REVISION = "f6a3d57ffe6888e64c873b3b18a945ca06673ff3"
WHISPER_MODEL = MODEL_DIR / "ggml-base.en-q5_1.bin"
KOKORO_MODEL = MODEL_DIR / "kokoro-v1.0.int8.onnx"
KOKORO_VOICES = MODEL_DIR / "voices-v1.0.bin"
ER2_MODEL = "gemini-robotics-er-2-streaming-preview"
SAMPLE_RATE = 16_000
MAX_AUDIO_SECONDS = 12
MAX_SPEECH_CHARS = 240
