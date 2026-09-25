# Architecture brief

## Outcome

Give a first-time visitor an immediate Stack-chan experience on a laptop: local
push-to-talk, local spoken reply, visible physics-backed motion, and an explicit
“track me” interaction. The demo must work without cloud credentials while keeping
Gemini Robotics ER2 as an opt-in brain.

## Chosen slice

The app reuses `qua121/stackchan-simulator` at one pinned commit rather than creating
another robot model. Its MuJoCo loop and Three.js scene remain the simulation
authority. The onboarding page imports only the scene and face renderers; the full
engineering dashboard is retained at `/sim/`. A small FastAPI integration layer owns
four adapters:

1. A deterministic local command router, or explicitly selected ER2 Live session.
2. Whisper base.en Q5_1 for local speech-to-text.
3. Kokoro-82M v1.0 int8 for local text-to-speech.
4. Browser-local MediaPipe face landmarks reduced to normalized x/y coordinates.

The typed command path is the acceptance baseline, so simulation behavior can be
tested without browser permission prompts. Voice and camera are additive paths.

## Runtime flow

```text
microphone -> float32 PCM -> localhost -> Whisper -> transcript
                                                    |
                                      local router or opt-in ER2
                                                    |
                       +----------------------------+------------------+
                       |                                               |
                guarded motion tools                         reply text
                       |                                               |
                  MuJoCo loop                                   Kokoro WAV
                       |                                               |
                  Three.js view                                  browser audio

webcam -> MediaPipe in browser -> smoothed face x/y -> localhost -> bounded pan/tilt
```

## Safety and privacy boundaries

- Default joint targets stay within yaw ±40° and pitch 10–80°.
- Face updates are smoothed and limited to 10 Hz; loss recenters after 0.9 seconds.
- Webcam frames never cross the browser boundary.
- ER2 is selected only by `--brain er2`; finding `GEMINI_API_KEY` does not enable it.
- Model and simulator downloads are pinned; large assets live under ignored `.local/`.
- The simulator's estimated dynamics are disclosed and are not treated as hardware
  calibration evidence.

## First acceptance proof

`./app smoke` must lint, run unit tests for routing/tracking/audio conversion, and
complete a deterministic command demo. A browser check then verifies that the
embedded dashboard receives WebSocket telemetry and visibly responds to a typed
`look left` command. Local speech is separately proven by synthesizing and then
transcribing a known phrase.
