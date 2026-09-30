"""LCD action client and local test panel; independent of LEGO and policy workers."""

import argparse
import html
import http.client
import json
import math
import re
import secrets
import struct
import subprocess
import tempfile
import threading
import time
import wave
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .drive_mode import DriveMode
from .speech import DEFAULT_VOICE, SPEECH, english_voices

EMOTIONS = ("neutral", "happy", "angry", "sad", "doubtful", "sleepy", "curious")
BMP_SIZE = 54 + 320 * 240 * 3
MAX_PCM_BYTES = 24000 * 2 * 20


@lru_cache(maxsize=1)
def available_voices():
    """Names, locales and sample phrases reported by the local macOS TTS engine."""
    try:
        result = subprocess.run(["/usr/bin/say", "-v", "?"], check=True,
                                capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError("Unable to list macOS voices") from error
    voices = []
    for line in result.stdout.splitlines():
        match = re.fullmatch(r"(.+?)\s+(\w+_\w+)\s+#\s*(.*)", line)
        if match:
            name, locale, sample = match.groups()
            voices.append((name.strip(), locale, sample))
    if not voices:
        raise RuntimeError("macOS reported no available voices")
    return tuple(sorted(voices, key=lambda v: (not v[1].startswith("en_"), v[1], v[0].casefold())))


def valid_voice(voice):
    if not isinstance(voice, str):
        return False
    if voice.startswith("kokoro:"):
        return voice.removeprefix("kokoro:") in english_voices()
    return any(voice == name for name, _, _ in available_voices())


def validate_pcm(pcm):
    if not isinstance(pcm, bytes) or not 0 < len(pcm) <= MAX_PCM_BYTES or len(pcm) % 2:
        raise ValueError("Expected up to 20 seconds of mono 24 kHz signed 16-bit PCM")


def synthesize_speech(text, voice=DEFAULT_VOICE):
    """Default neural Kokoro speech on the Mac; installed system voices remain optional."""
    if not isinstance(text, str) or not text.strip() or len(text) > 240:
        raise ValueError("Enter 1–240 characters")
    if not valid_voice(voice):
        raise ValueError("Choose an available voice")
    if voice.startswith("kokoro:"):
        pcm = SPEECH.synthesize(text, voice.removeprefix("kokoro:"))
        validate_pcm(pcm)
        return pcm
    with tempfile.TemporaryDirectory(prefix="stackchan-speech-") as folder:
        audio = Path(folder) / "speech.aiff"
        try:
            subprocess.run(["/usr/bin/say", "-v", voice, "-r", "170", "-o",
                            str(audio), "--", text], check=True, capture_output=True, timeout=20)
            result = subprocess.run([
                "ffmpeg", "-v", "error", "-i", str(audio), "-af",
                "adelay=200,apad=pad_dur=0.3", "-ar", "24000", "-ac", "1",
                "-f", "s16le", "pipe:1",
            ], check=True, capture_output=True, timeout=20)
        except (OSError, subprocess.SubprocessError) as error:
            raise RuntimeError("Local speech generation failed; requires Mac say and ffmpeg") from error
    validate_pcm(result.stdout)
    return result.stdout


def validate_action(action):
    if not isinstance(action, dict) or not action:
        raise ValueError("Expected a face action object")
    for key, value in action.items():
        if key == "emotion":
            if value not in EMOTIONS:
                raise ValueError("Unknown emotion")
        elif key not in ("talking", "auto_cycle", "animated") or type(value) is not bool:
            raise ValueError("Unknown field or invalid boolean")


class FaceClient:
    def __init__(self, camera_url, key, *, port=81, timeout=3):
        self.host = urlsplit(camera_url).hostname
        if not self.host or not key:
            raise ValueError("Camera URL and stream key required")
        self.port, self.timeout, self.key = port, timeout, key

    def _request(self, path, action=None):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
        try:
            body = None if action is None else json.dumps(action)
            connection.request(
                "GET" if body is None else "POST", path, body,
                {"X-Stream-Key": self.key, "Content-Type": "application/json"},
            )
            response = connection.getresponse()
            if response.status == 404:
                raise RuntimeError("Install the emotion-face firmware update first")
            if response.status != 200:
                raise RuntimeError(f"Face controller returned HTTP {response.status}")
            limit = BMP_SIZE if path == "/face.bmp" else 8192
            data = response.read(limit + 1)
            if len(data) > limit:
                raise RuntimeError("Oversized face response")
            return data
        finally:
            connection.close()  # Each request can recover after a Wi-Fi outage.

    def state(self):
        return self._state(self._request("/face"))

    def send(self, **action):
        validate_action(action)
        return self._state(self._request("/face", action))

    @staticmethod
    def _state(data):
        state = json.loads(data)
        if not isinstance(state, dict) or not state.get("renderer_ready"):
            raise RuntimeError("Face renderer is not ready")
        if state.get("emotion") not in EMOTIONS or state.get("visible_emotion") not in EMOTIONS:
            raise RuntimeError("Invalid emotion state")
        return state

    def snapshot(self):
        data = self._request("/face.bmp")
        if (len(data) != BMP_SIZE or data[:2] != b"BM"
                or struct.unpack_from("<IiiHH", data, 14) != (40, 320, -240, 1, 24)
                or struct.unpack_from("<I", data, 10)[0] != 54):
            raise RuntimeError("Invalid board-rendered snapshot")
        return data

    def head_state(self):
        return json.loads(self._request("/head"))

    def set_head(self, mode):
        if mode not in ("release", "resume"):
            raise ValueError("Choose manual posing or powered hold")
        return json.loads(self._request("/head", {"mode": mode, "pan": 0, "tilt": 0}))

    def speech_state(self):
        return json.loads(self._request("/speech"))

    def speak_pcm(self, pcm):
        validate_pcm(pcm)
        connection = http.client.HTTPConnection(self.host, self.port, timeout=10)
        try:
            connection.request("POST", "/speech", pcm,
                               {"X-Stream-Key": self.key,
                                "Content-Type": "application/octet-stream"})
            response = connection.getresponse()
            data = response.read(8193)
            if response.status == 409:
                raise RuntimeError("Stack Chan is already speaking; wait until it finishes")
            if response.status != 202 or len(data) > 8192:
                raise RuntimeError(f"Speech upload rejected: HTTP {response.status}")
            return json.loads(data)
        finally:
            connection.close()


class MacSpeech:
    """Local playback continues after the browser loses focus; never queue takes."""

    def __init__(self):
        self.lock = threading.Lock()
        self.current = {"busy": False, "phase": "idle", "error": ""}
        self.deadline = 0

    def state(self):
        with self.lock:
            return {**self.current, "remaining_seconds": max(0, math.ceil(self.deadline - time.monotonic()))}

    def start(self, text, voice):
        with self.lock:
            if self.current["busy"]:
                return False
            self.deadline = time.monotonic() + 5
            self.current = {"busy": True, "phase": "preparing", "error": ""}
        threading.Thread(target=self._play, args=(text, voice), daemon=True).start()
        return True

    def _phase(self, phase, *, busy=True, error=""):
        with self.lock:
            self.current = {"busy": busy, "phase": phase, "error": error}

    def _play(self, text, voice):
        try:
            pcm = synthesize_speech(text, voice)
            with tempfile.TemporaryDirectory(prefix="stackchan-mac-speech-") as folder:
                path = Path(folder) / "speech.wav"
                with wave.open(str(path), "wb") as audio:
                    audio.setnchannels(1)
                    audio.setsampwidth(2)
                    audio.setframerate(24000)
                    audio.writeframes(pcm)
                self._phase("countdown")
                time.sleep(max(0, self.deadline - time.monotonic()))
                self._phase("playing")
                subprocess.run(["/usr/bin/afplay", str(path)], check=True,
                               capture_output=True, timeout=25)
            self._phase("complete", busy=False)
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
            self._phase("error", busy=False, error="Mac playback failed; check the voice and audio output")


def make_panel(client, token, mac_speech=None, drive_mode=None):
    mac_speech = mac_speech or MacSpeech()
    prefix = f"/{token}"
    options = '<optgroup label="Kokoro · local neural speech">' + "".join(
        f'<option value="kokoro:{name}"{" selected" if name == "am_puck" else ""}>'
        f'{name} · {"British" if name.startswith("b") else "American"} English</option>'
        for name in english_voices()
    ) + '</optgroup><optgroup label="macOS · system speech">' + "".join(
        f'<option value="{html.escape(name, quote=True)}"'
        f'>{html.escape(name)} · {html.escape(locale)}</option>'
        for name, locale, _ in available_voices()
    ) + "</optgroup>"
    page = (Path(__file__).with_name("faces.html").read_text().replace("__BASE__", prefix)
            .replace("__VOICE_OPTIONS__", options))

    class Panel(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, *_):
            pass  # Do not log private URL tokens or device credentials.

        def respond(self, code, body, content_type="application/json"):
            if content_type == "application/json":
                body = json.dumps(body).encode()
            elif isinstance(body, str):
                body = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; "
                             "script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                             "img-src 'self' blob:; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlsplit(self.path).path
            try:
                if path in (prefix, prefix + "/"):
                    return self.respond(200, page, "text/html; charset=utf-8")
                if path == prefix + "/drive":
                    return self.respond(200, drive_mode.state() if drive_mode else {"active": False, "phase": "unavailable", "error": "Driving mode unavailable"})
                if path == prefix + "/mac-speech":
                    return self.respond(200, mac_speech.state())
                if path == prefix + "/state":
                    return self.respond(200, client.state())
                if path == prefix + "/snapshot":
                    return self.respond(200, client.snapshot(), "image/bmp")
                if path == prefix + "/head":
                    return self.respond(200, client.head_state())
                if path == prefix + "/speech":
                    return self.respond(200, client.speech_state())
                self.respond(404, {"error": "Not found"})
            except (OSError, RuntimeError, ValueError, http.client.HTTPException):
                self.respond(503, {"error": "Stack Chan unavailable; check Wi-Fi or firmware"})

        def do_POST(self):
            path = urlsplit(self.path).path
            if path not in (prefix + "/action", prefix + "/speak", prefix + "/head", prefix + "/mac-speak", prefix + "/drive"):
                return self.respond(404, {"error": "Not found"})
            expected_origin = f"http://127.0.0.1:{self.server.server_port}"
            if self.headers.get("Origin") != expected_origin:
                return self.respond(403, {"error": "Same-origin actions only"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if (not 0 < length <= (1024 if path in (prefix + "/speak", prefix + "/mac-speak") else 200)
                        or self.headers.get("Content-Type") != "application/json"):
                    raise ValueError("Expected a small JSON action")
                action = json.loads(self.rfile.read(length))
                if path == prefix + "/drive":
                    if (not isinstance(action, dict) or set(action) != {"action"}
                            or action["action"] not in ("start", "stop")):
                        raise ValueError("Choose load or stop driving mode")
                elif path == prefix + "/action":
                    validate_action(action)
                elif path == prefix + "/head":
                    if (not isinstance(action, dict) or set(action) != {"mode"}
                            or action["mode"] not in ("release", "resume")):
                        raise ValueError("Choose manual posing or powered hold")
                elif (not isinstance(action, dict) or set(action) not in ({"text"}, {"text", "voice"})
                      or not isinstance(action["text"], str)
                      or not 0 < len(action["text"].strip()) <= 120
                      or not valid_voice(action.get("voice", DEFAULT_VOICE))):
                    raise ValueError("Enter 1–120 characters and choose an available voice")
            except ValueError as error:
                return self.respond(400, {"error": str(error)})
            try:
                if path == prefix + "/drive":
                    if drive_mode is None:
                        return self.respond(503, {"error": "Driving mode unavailable"})
                    if action["action"] == "stop":
                        return self.respond(202, drive_mode.stop())
                    if not drive_mode.start():
                        return self.respond(409, {"error": "Driving mode is already active"})
                    return self.respond(202, drive_mode.state())
                if path == prefix + "/mac-speak":
                    if not mac_speech.start(action["text"], action.get("voice", DEFAULT_VOICE)):
                        return self.respond(409, {"error": "Mac speech is already scheduled or playing"})
                    return self.respond(202, mac_speech.state())
                if path == prefix + "/head":
                    if drive_mode and drive_mode.state()["active"]:
                        return self.respond(409, {"error": "Stop driving mode before changing head positioning"})
                    return self.respond(200, client.set_head(action["mode"]))
                if path == prefix + "/speak":
                    not_before = time.monotonic() + 5
                    if client.speech_state().get("busy"):
                        return self.respond(409, {"error": "Stack Chan is already speaking"})
                    pcm = synthesize_speech(action["text"], action.get("voice", DEFAULT_VOICE))
                    time.sleep(max(0, not_before - time.monotonic()))
                    return self.respond(202, client.speak_pcm(pcm))
                self.respond(200, client.send(**action))
            except (OSError, RuntimeError, ValueError, http.client.HTTPException):
                self.respond(503, {"error": "Action not confirmed; check Stack Chan and retry"})

    return Panel


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(".local/camera.json"))
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    client = FaceClient(config["url"], config["key"])
    token = secrets.token_urlsafe(24)
    drive_mode = DriveMode(client, args.config)
    with ThreadingHTTPServer(("127.0.0.1", args.port), make_panel(client, token, drive_mode=drive_mode)) as server:
        print(f"Stack Chan control panel: http://127.0.0.1:{server.server_port}/{token}", flush=True)
        print("Face and speech actions. Ctrl+C closes the panel; on-board clips finish normally.",
              flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            drive_mode.close()


if __name__ == "__main__":
    main()
