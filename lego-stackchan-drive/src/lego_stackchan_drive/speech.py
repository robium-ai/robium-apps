"""Local Kokoro speech, reusing the Stack Chan simulator / Silly TurtleBot contract."""

import argparse
import hashlib
import shutil
import tempfile
import threading
from functools import lru_cache
from pathlib import Path
from urllib.request import urlopen

import numpy as np

MODEL_DIR = Path(__file__).resolve().parents[2] / ".local/models"
MODEL_NAME = "kokoro-v1.0.int8.onnx"
VOICES_NAME = "voices-v1.0.bin"
ASSETS = {
    MODEL_NAME: "6e742170d309016e5891a994e1ce1559c702a2ccd0075e67ef7157974f6406cb",
    VOICES_NAME: "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d",
}
ASSET_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
DEFAULT_VOICE = "kokoro:am_puck"
RATE = 24000
MAX_SECONDS = 20


def verified(path, digest):
    return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == digest


def setup_assets(reuse=None):
    """Install verified pinned assets into this app's ignored cache, atomically."""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    for name, digest in ASSETS.items():
        target = MODEL_DIR / name
        if verified(target, digest):
            continue
        with tempfile.NamedTemporaryFile(dir=MODEL_DIR, delete=False) as output:
            temporary = Path(output.name)
            try:
                source = None if reuse is None else reuse / name
                if source is not None and verified(source, digest):
                    with source.open("rb") as data:
                        shutil.copyfileobj(data, output)
                else:
                    with urlopen(ASSET_URL + name, timeout=60) as data:
                        shutil.copyfileobj(data, output)
                output.flush()
                if not verified(temporary, digest):
                    raise RuntimeError(f"Kokoro asset checksum mismatch: {name}")
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
        print(f"Ready: {name}", flush=True)


@lru_cache(maxsize=1)
def english_voices():
    path = MODEL_DIR / VOICES_NAME
    if not verified(path, ASSETS[VOICES_NAME]):
        raise RuntimeError("Kokoro voices missing or invalid; run ./app build-voices")
    with np.load(path, allow_pickle=False) as voices:
        return tuple(sorted(name for name in voices.files if name[:2] in ("af", "am", "bf", "bm")))


def pcm16(samples, sample_rate):
    """Enforce the board's fixed audio format, including headroom and silence padding."""
    audio = np.asarray(samples)
    if (sample_rate != RATE or audio.ndim != 1 or not audio.size
            or not np.isfinite(audio).all() or audio.size > int((MAX_SECONDS - 0.5) * RATE)):
        raise ValueError("Expected finite mono 24 kHz audio, at most 19.5 seconds before padding")
    # Asymmetric scaling preserves both signed endpoints without wrapping +1 to -32768.
    audio = np.clip(audio, -1.0, 1.0)
    encoded = np.rint(audio * np.where(audio < 0, 32768, 32767)).astype("<i2").tobytes()
    return bytes(int(0.2 * RATE) * 2) + encoded + bytes(int(0.3 * RATE) * 2)


class KokoroSpeech:
    def __init__(self):
        self._engine = None
        self._lock = threading.Lock()

    def synthesize(self, text, voice="am_puck"):
        if not isinstance(text, str) or not 0 < len(text.strip()) <= 240:
            raise ValueError("Enter 1–240 characters")
        if voice not in english_voices():
            raise ValueError("Choose an available English Kokoro voice")
        with self._lock:
            if self._engine is None:
                if not verified(MODEL_DIR / MODEL_NAME, ASSETS[MODEL_NAME]):
                    raise RuntimeError("Kokoro model missing or invalid; run ./app build-voices")
                from kokoro_onnx import Kokoro

                self._engine = Kokoro(str(MODEL_DIR / MODEL_NAME), str(MODEL_DIR / VOICES_NAME))
            samples, sample_rate = self._engine.create(
                text.strip(), voice=voice, speed=1.03,
                lang="en-gb" if voice.startswith("b") else "en-us",
            )
        return pcm16(samples, sample_rate)


SPEECH = KokoroSpeech()


def main():
    parser = argparse.ArgumentParser(description="Install pinned local Kokoro assets")
    parser.add_argument("--reuse", type=Path, help="Optional existing model cache to verify and copy")
    args = parser.parse_args()
    setup_assets(args.reuse)
    print(f"Kokoro ready · {len(english_voices())} English voices · default am_puck")


if __name__ == "__main__":
    main()
