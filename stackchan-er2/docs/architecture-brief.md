# Architecture Brief: STACK-CHAN ER 2 Companion

**Date:** 2026-09-16
**Status:** active

## Goal and constraints

Create a simple voice-first application for the connected M5Stack STACK-CHAN
K151. The robot continuously listens for speech addressed to “Stack Chan,” and
Gemini Robotics ER 2 may answer through the onboard speaker, move the pan/tilt
head, show short text on the display, or request one fresh camera observation
when a question requires current visual evidence. It can also select one of
five guarded head animations: quick yes/no gestures, privacy, turn back, and
look straight.

The app deliberately excludes continuous image streaming, a local wake-word
engine, web UI, long-term memory, ROS, simulation, and autonomous behavior.
The connected robot was identified over USB as an ESP32-S3 running M5Stack's
factory `stack-chan` 1.5.1 firmware before the companion-firmware change.

## Decisions

| Decision | Choice | Why now | Confidence |
|---|---|---|---|
| Interaction | Continuous 250 ms microphone chunks with Gemini automatic VAD; `--push-to-talk` remains a fallback | Removes keyboard interaction while retaining the proven manual mode | validated by bounded live continuous command and real hardware audio handoff |
| Embodied model | `gemini-robotics-er-2-streaming-preview` in one persistent Live API session | Current ER 2 endpoint accepts streamed audio and supports blocking function calls | validated against current Google documentation and the existing `silly-turtlebot` implementation |
| Host environment | Native macOS Python 3.12 with uv and a committed lockfile | Pure Python, direct USB access, and built-in `say`/`afconvert` TTS; Docker adds no value | validated by `robium-ai doctor` |
| Device environment | Arduino ESP32 3.3.11, StackChan-BSP 1.1.0, M5Unified 0.2.20, and ArduinoJson 7.4.3 under project-local `.arduino` | Uses M5Stack's maintained K151 hardware support while keeping tool versions explicit; 0.2.20 is the newest M5Unified release with STACK-CHAN audio support and the BSP-compatible I/O-expander API | validated by real compile and flash |
| Host/device boundary | One blocking USB serial request at a time; newline JSON for control and acknowledged 240-byte signed 16-bit PCM chunks for speech | Human-rate actions need simplicity and debuggability more than a network service; acknowledgement prevents CoreS3's 256-byte USB receive buffer from dropping a burst | validated by real mic/speaker smoke |
| Speech | macOS TTS rendered to 16 kHz mono PCM and played on STACK-CHAN | ER 2 Streaming returns text, not generated audio; this keeps TTS independently replaceable | validated by real onboard-speaker smoke |
| Vision | Model-selected `look` tool captures one 320×240 JPEG from the CoreS3 GC0308 camera and attaches it as inline media to the matching function response | Gives ER 2 current visual evidence without continuously sending images, and deterministically binds each observation to its tool call | validated by repeated real-camera capture and physical mic → ER 2 → vision → speech smoke |
| Expressive motion | One enum-only `animate` tool backed by firmware-owned keyframes | Lets the model select expressive gestures without exposing raw servo mode, durations, or extended angles | validated by host tests, real nod/shake/privacy motion, front → rear → front camera evidence, and a silent live ER 2 call |

## Module boundaries and communications

| Module | Rate / failure domain | Boundary |
|---|---|---|
| Gemini host process | Continuous 250 ms input rate; API/network failures must not produce unguarded actions | Concurrent audio-send and response/tool loops in one persistent Live API session; every function call crosses `GuardedActions` |
| USB device adapter | One blocking request at a time; serial disconnect is independent of the model | Compact newline JSON plus exact-length PCM on `/dev/cu.usbmodem*`; its lock bounds tool latency to at most the active mic chunk |
| STACK-CHAN firmware | Owns servos, screen, mic, speaker, and camera; remains safe if the host disappears | Enforces the same head/audio/image limits again before touching hardware |

## Provisional assumptions and risks

| Assumption or risk | Impact | Cheapest validation | Authorized pivot |
|---|---|---|---|
| Opening native USB resets the ESP32-S3 | Startup has a short delay | Reconnect and ping until firmware answers | Keep the retry handshake; no architecture change |
| Factory servo calibration survives a normal Arduino upload in NVS | Lost calibration could make motion unsafe | Back up the full flash, query current angles, and use only a 10-degree yaw smoke | Restore the backup and add an explicit calibration command before further motion |
| One full utterance fits PSRAM and acknowledged USB transfer latency is acceptable | Long replies could fail or feel slow | The real board reports 8 MB PSRAM; cap speech to 240 characters / 40 seconds and use 240-byte acknowledged chunks | Reduce reply length or move to streamed playback without changing the model/tool boundary |
| Mic and speaker cannot run simultaneously | Full duplex and barge-in are unavailable | Pause the audio loop before tools, switch to speaker, then restart mic chunks automatically | Retain half-duplex continuous listening; use `--push-to-talk` if the room is too noisy |
| Room audio is continuously sent to Gemini | Higher API usage and a privacy trade-off while the app runs | Require an explicit launch, visible green listening LEDs, and Control-C stop | Add a local wake-word detector later if continuous cloud streaming is undesirable |
| Camera frames could expose unintended surroundings | Visual data leaves the device when a visual answer is requested | Keep vision behind an explicit model tool; capture and send exactly one frame per call; document the local-only camera probe | Add a physical camera-disable flag if deployment needs a stronger privacy control |
| Continuous yaw is velocity/time based rather than an absolute 180° target | `turn_back` can vary slightly with battery and friction | Use a fixed bounded half-turn, retain an explicit facing-back state, and make `look_straight` reverse then center | Tune only the firmware-owned duration from physical camera evidence; do not expose it to the model |
| A Gemini key is available outside git | Live model turn cannot run otherwise | `./app doctor` checks presence without printing it | Run through the maintainer's chosen secret injection command |

## Implementation path

1. Build and pass the fake-device action/guard smoke test.
2. Save a private factory-flash backup, compile, flash, and pass a bounded real
   hardware smoke covering display, 10-degree yaw motion, microphone capture,
   and onboard speech.
3. Run one supervised ER 2 turn such as “Look left, say hello, and show Welcome.”

All three initial steps passed on 2026-09-14. The supervised ER 2 turn used a
Doppler-injected `GEMINI_API_KEY` without storing or printing it; Gemini moved
the head, spoke “Hello!”, and displayed “Welcome” through successful guarded
tool calls.

On 2026-09-16, continuous listening became the default. Seventeen tests pass;
firmware 0.2.0 passed repeated real 250 ms mic capture, speaker handoff, mic
resume, and clean stop. A bounded continuous Live API test heard “Stack Chan,”
invoked guarded speech, and cleaned up the listening state. The final physical
end-to-end smoke sent a Mac-spoken command through STACK-CHAN's real microphone;
ER 2 invoked `speak`, the onboard speaker said “Continuous microphone streaming
works!”, listening resumed, and Control-C stopped it cleanly.

On 2026-09-16, firmware 0.3.0 added model-selected vision. The GC0308 shares
its SCCB pins with STACK-CHAN's internal I2C peripherals, so each `look` call
temporarily releases M5Unified's bus, captures and encodes one 320×240 JPEG,
deinitializes the camera, and restores internal I2C before audio or RGB access.
Twenty tests and repeated real camera → microphone → speaker recovery pass. A
physical continuous-listening turn heard “Stack Chan, what do you see,” called
`look` exactly once, described the observed bowl, spoke the answer onboard, and
resumed listening. Separate live turns confirmed ordinary speech does not call
`look` and “only display; do not speak” calls `show_text` without `speak`.

The initial implementation sent each still through `send_realtime_input(video)`
immediately before its tool response. Realtime media processing is not
deterministically ordered, so later visual questions could be answered from an
older image already in session context. The image now travels in
`FunctionResponse.parts`, binding the JPEG to the exact `look` call; a unit
regression asserts that `look` emits no realtime-video message. The live ER 2
endpoint accepted the inline media, and a single-session physical regression
moved the camera between opposite views: the first response described the
laptop and its red sticker, while the second described the person in the new
view rather than reusing the earlier image.

Firmware 0.4.0 adds five enum-only animation sequences. Ordinary `move_head`
remains constrained to the conversational range, while `privacy` intentionally
uses the hardware's 90° pitch endpoint and `turn_back` uses the K151's
continuous 360° yaw mode for a timed half-turn. `look_straight` tracks the
rear-facing state, reverses the half-turn, and then returns to yaw 0° / pitch
45°. Because the servo's PWM-mode registers survive an ESP32 reset while the
BSP's in-memory mode cache does not, firmware startup explicitly restores the
yaw position limits before centering; a real reconnect recovered a deliberately
rear-facing servo. Twenty-four host tests cover the enum guard, every named
option, serial framing, and the rule that animation-only turns must not trigger
fallback speech. Physical front/rear/front captures were distinct and the final
pose measured yaw −1° / pitch 43°. A Doppler-injected live ER 2 request, “Nod
yes quickly. Do not speak,” called only `animate(nod_yes)` and produced no
speech or display action.
