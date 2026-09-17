# STACK-CHAN ER 2 Companion

Talk to a real M5Stack STACK-CHAN K151. Gemini Robotics ER 2 can answer through
the robot's speaker, make a small pan/tilt gesture, show a short message on its
display, perform named head animations, and inspect a fresh onboard-camera
image when a question requires it.

The default mode continuously streams short microphone chunks. Say “Stack Chan”
followed by a command or question; Gemini detects the speech boundary and may
answer, move, display text, or take one camera image. Images are not streamed:
ER 2 calls the `look` tool only when it needs current visual evidence. The app
pauses listening while a physical tool runs, then resumes automatically. It does
not use a local wake-word engine or autonomous behavior.

## Quick start

The firmware flash replaces M5Stack's factory firmware. Save the restorable
private backup first; it may contain Wi-Fi credentials, so `.local/` is ignored
by git.

```bash
./app build
./app firmware-setup
./app firmware-backup
./app firmware-flash
./app device-doctor
./app hardware-smoke
```

Then inject the Gemini API key from Doppler without printing or committing it:

```bash
doppler run --project robium --config dev -- ./app run
```

Say something such as “Stack Chan, what do you see in front of you?” ER 2 will
request one fresh camera image before answering. Ordinary conversation does not
capture or send images. You can also say “Only display Welcome; do not speak,”
which performs the display action without a spoken acknowledgement.

Named animations are also available by voice. Try “Stack Chan, nod yes,”
“Stack Chan, shake your head no,” “Stack Chan, privacy,” “Stack Chan, turn your
back,” or “Stack Chan, look straight.” Animation-only requests do not produce a
spoken acknowledgement.

The green body LEDs indicate listening. Press Control-C to stop. Continuous mode
sends room audio to Gemini and consumes Live API usage while running.

The previous keyboard-triggered mode remains available as a fallback:

```bash
doppler run --project robium --config dev -- ./app run --push-to-talk
```

A text-only input is useful for diagnosis:

```bash
doppler run --project robium --config dev -- \
  ./app run --text "Look left, say hello, and show Welcome."
```

## Commands

```text
./app doctor            host, key, and USB preflight
./app demo              deterministic fake-device actions
./app smoke             lint, unit tests, and fake end-to-end smoke
./app firmware-build    compile without touching the device
./app firmware-flash    build and upload to /dev/cu.usbmodem1101
./app device-doctor     query firmware and current head angles
./app hardware-smoke    bounded real display/head/mic/speaker check
./app camera            save one fresh image as stackchan-view.jpg
./app animate NAME      run nod_yes, shake_no, privacy, turn_back, or look_straight
./app run               continuous ER 2 voice-command session
./app run --push-to-talk
                        press Enter for each four-second recording
./app tools             model-visible capability list
```

Override the serial device when needed:

```bash
STACKCHAN_PORT=/dev/cu.usbmodem1201 ./app firmware-flash
./app device-doctor --port /dev/cu.usbmodem1201
```

## Safety and limits

The model sees five semantic tools: move, display, speak, an on-demand
single-image `look`, and a named `animate` action. Both Python and firmware
enforce yaw `-45..45°`, pitch `5..85°`, speed `100..400`, short display text,
and bounded speech for ordinary model-selected movement. The animation tool
accepts only five exact names: `nod_yes` and `shake_no` are quick gestures;
`privacy` uses the K151 pitch endpoint of 90°; `turn_back` uses the yaw servo's
continuous-rotation mode for an approximately 180° half-turn; and
`look_straight` reverses that half-turn and centers at yaw 0°, pitch 45°. There
is no raw-servo or arbitrary binary model tool. Keep the full circle around the
head clear during motion and never force a powered joint by hand.

The camera remains absent from the Live API input until ER 2 calls `look`. That
call pauses microphone chunks, captures and JPEG-encodes one 320×240 frame on
the CoreS3, attaches it directly to that `look` function response, and then
resumes listening. It is never inserted into the independent realtime-video
stream. Use `./app camera` to test the camera without sending the image to
Gemini.

Audio is signed 16-bit, little-endian, mono PCM at 16 kHz. Listening uses
continuous 250 ms device chunks and Gemini server-side voice detection. The
firmware switches between microphone and speaker because the CoreS3 audio path
cannot use both at once. Speech crosses USB in acknowledged 240-byte chunks so
the CoreS3 receive buffer cannot silently drop a large PCM burst. macOS `say` is
the initial replaceable TTS adapter; Gemini Robotics ER 2 Streaming supplies
text and function calls rather than synthesized audio.

## Restoring factory firmware

The easiest supported path is M5Burner and the official STACK-CHAN factory
image. The private 16 MB file created by `./app firmware-backup` is an additional
device-specific recovery copy and must not be committed or shared.

## References

- [Gemini Robotics ER 2](https://ai.google.dev/gemini-api/docs/robotics-overview)
- [Gemini Robotics ER 2 Streaming](https://ai.google.dev/gemini-api/docs/robotics-streaming)
- [M5Stack STACK-CHAN source](https://github.com/m5stack/StackChan)
- [M5Stack StackChan-BSP](https://github.com/m5stack/StackChan-BSP)
- [M5Stack CoreS3 camera example](https://docs.m5stack.com/en/arduino/m5cores3/camera)
