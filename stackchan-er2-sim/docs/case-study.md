# Stack-chan ER2 Simulator case study

## Problem

The physical Stack-chan ER2 demo has strong personality but asks a new visitor to
bring hardware, firmware, audio devices, and an API key before seeing anything move.

## POC

This app moves the first experience to a browser-backed MuJoCo model. The default
brain is deterministic and credential-free. Whisper and Kokoro keep the speech loop
local, while a browser-local MediaPipe tracker implements “track me” without sending
camera frames to the server or ER2.

## Verification

Run `./app smoke` for the reproducible software checks. Run `./app run`, issue a typed
`look left`, and inspect the embedded simulator for the visible acceptance check.
Voice round-trip and camera checks require the corresponding local permissions.

## Known gaps

- MediaPipe web assets are pinned but downloaded on first tracker use rather than by
  `./app build`.
- The MuJoCo mass and servo profiles are estimates, not a calibrated digital twin.
- The POC supports English local STT/TTS and largest-face tracking only.
