# Stack-chan ER2 Simulator

A local-first onboarding demo for Stack-chan: speak a short command, see a 2-DOF
MuJoCo model react, hear a local neural voice, and optionally let the robot follow
your face. No API key is needed for the default path.

![Stack-chan responding in the local MuJoCo demo](assets/stills/stackchan-er2-sim-macos.png)

## Quick start

```bash
./app build
./app run
```

The first build downloads about 185 MB of pinned runtime assets, plus the locked
Python environment. `./app run` opens
<http://127.0.0.1:8017>. Try:

- `Introduce yourself`
- `Look left` / `Look right` / `Look up` / `Look down`
- `Nod yes` / `Shake no`
- `Show what you can do`
- `Track me` / `Stop tracking`

You can type commands or hold the microphone button. Camera and microphone access
are requested only after the corresponding button or command is used.

With Robium installed, you can check and run the app from any directory:

```bash
npx robium-ai app doctor stackchan-er2-sim
npx robium-ai app run stackchan-er2-sim
```

## Local models and privacy

- STT: Whisper `base.en` Q5_1 through `pywhispercpp`
- TTS: Kokoro-82M v1.0 int8, voice `am_puck`
- Face tracking: MediaPipe Face Landmarker in the browser
- Physics and rendering: the pinned unofficial
  [`qua121/stackchan-simulator`](https://github.com/qua121/stackchan-simulator)

Audio PCM is sent only to the local FastAPI process. Webcam frames stay in the
browser; only normalized, smoothed face-center coordinates are sent to localhost.
MediaPipe runtime/model files are fetched from their pinned public CDNs the first
time tracking starts. The simulator, Whisper, and Kokoro assets are downloaded and
cached by `./app build` with pinned revisions or SHA-256 checksums.

## Optional Gemini Robotics ER2 brain

The presence of a key never changes the default mode. Opt in explicitly:

```bash
export GEMINI_API_KEY=...
./app run --brain er2
```

Whisper and Kokoro remain local in ER2 mode. Only the transcript and ER2 tool/result
messages go to the Gemini API; webcam frames do not.

## Useful commands

```bash
./app doctor
./app demo
./app smoke
./app run --no-open
```

The onboarding page renders only the live robot, face, and speech bubble. The
upstream engineering dashboard remains an internal implementation detail.

## Provenance and limits

This app's original code is MIT-licensed. Its downloaded dependencies and model
assets retain their upstream licenses:

- [`qua121/stackchan-simulator`](https://github.com/qua121/stackchan-simulator),
  Apache-2.0, pinned at commit `f6a3d57ffe68`
- [whisper.cpp](https://github.com/ggml-org/whisper.cpp), MIT, with the pinned
  English-only `base.en` Q5_1 model
- [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M), Apache-2.0, through
  the MIT-licensed `kokoro-onnx` runtime
- [MediaPipe](https://github.com/google-ai-edge/mediapipe), Apache-2.0

The simulator uses CAD-derived geometry plus estimated mass and servo profiles;
this POC is suitable for interaction prototyping, not calibrated hardware
prediction. Mesh and font notices included by the pinned simulator remain with
their upstream files. The browser tracker selects the largest face, smooths its
center, rate-limits updates to 10 Hz, and returns to center after losing the face.
