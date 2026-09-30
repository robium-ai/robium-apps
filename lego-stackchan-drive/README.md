# Stack Chan learns to drive

Mount an M5Stack Stack Chan on a LEGO Technic car, drive it with a controller,
and collect the camera images and steering commands needed to train a small
ACT policy. The Mac owns joystick input, Pybricks Bluetooth motor control,
camera capture over Wi-Fi, training data, and local policy inference. Stack
Chan supplies the camera, expressive face, head motion, and speaker.

Watch the [finished driving video](https://www.youtube.com/watch?v=_1pQTt8gqZM)
and read the short [build and training tutorial](docs/case-study.md), including
the camera-angle and direction lessons, guardrail-course trial, and real camera
view. This app requires the physical LEGO hub, two motors on ports D and B, a Stack Chan K151,
and a Mac with Bluetooth LE and access to the robot's 2.4 GHz Wi-Fi network.
There is no hosted robot session. The [training record](docs/training-results.md)
separates the first road-following experiment, later black-tape comparison, and
guardrail-course model. Filmed track trials use additional data and must not be
inferred from the first checkpoint's offline score.

## Run

```bash
./app build
./app check
./app probe --video-only --seconds 60  # isolate camera timing, no actuators
./app run --camera-only               # camera + startup centering, no LEGO
./app run --video-only                # preview only; R starts/stops saving camera images
./app run --input-test-seconds 10 --root .local/joystick-tests # gamepad/image test, no actuators
./app probe --seconds 15               # camera + BLE, zero motor power only
./app run --task "follow the toy road"
```

The hub program in `hub/main.py` uses **left D, right B**. Both control axes were
reversed after the operator reported opposite motion: host throttle sign is +1
and steering sign is -1. D/B connectivity has passed real READY/PONG; the corrected
physical directions await the operator's recheck. Default full throttle is now 75%
motor power (3× the original), with steering strength at 25%. `--power`
sets the base power (10–40); throttle uses 3× and steering 1× that value, each
capped at 100%. Combined
turns scale both wheel powers together to stay within the throttle maximum. The robot must be in view and within reach for the first check.

- **Left stick vertical:** forward/backward throttle, at 3× the original motor power.
- **Right stick horizontal:** left/right steering. Left horizontal and right vertical are ignored. Arrows/WASD also work.
- **Camera:** targets pan 0° / tilt 0° at startup, then holds that pose. Neither stick controls it. Press **T** to tilt up or **G** to tilt down in 5° steps (0–85°) in the driving window. This works while holding Space or R1; camera angle changes can reduce the centered-camera model’s accuracy.
- **Driving:** automatic whenever the connections and live video are ready; no arm/disarm step. Gamepad input works while the window is unfocused.
- **Hold L2 or R2:** record an episode; the display counts images, paired actions, and BLE writes separately. Releasing both automatically saves the clip without a success/rejection label. Switching between triggers while at least one remains held keeps the same clip. R/F/X are no longer recording controls.
- **Video-only mode:** click the preview window and press **R** to start recording, then **R** again to save. JPEG images and timestamps are saved under `.local/video-captures/<clip>/frames/` and `events.jsonl`. No controller is required; LEGO and head control remain disabled.
- **Q / Escape:** stop and close; an unfinished episode is marked interrupted.

Point and securely mount the camera toward the road before useful collection.
The camera centers before driving is available and can then be tilted with T/G; keep the training camera pose consistent during collection.
Startup centering waits for servo feedback within 2° of the 0° / 0° target.
Record short, repeatable
road segments with varied starting offsets. Reject collisions or unsuccessful
runs. Keep complete runs together when making training/validation splits.

## Manual posing for stop-motion shots (firmware 0.6.6)

The current filming setup boots with both head servos released and the new
**curious** face: open eyes, slightly raised brows, and a downward gaze. This is
an expression, not visual tracking. The audio bars remain unchanged.

Manual posing persists across reboot. While released, ordinary head position
commands receive HTTP 409 and cannot re-enable torque. `hold` also leaves the
servos released. Resume explicitly before using the driving app's startup centering:

```bash
uv run python - <<'PYTHON'
import json
from pathlib import Path
from lego_stackchan_drive.head import HeadClient
config = json.loads(Path('.local/camera.json').read_text())
head = HeadClient(config['url'], config['key'])
print(head.resume())  # Restore powered hold at the current pose.
# head.release()      # Release both axes again for manual posing.
head.close()
PYTHON
```

Manual posing now disables the servo power rail, not only UART torque. The PY32
VM_EN output latch is read back before camera startup. `GET /head`
reports `servo_power_enabled`, `servo_power_verified`, and `release_applied`;
angles are null while unpowered. Changing between manual and powered mode
restarts the board to keep shared I2C access out of the camera session. Powered
mode holds the current pose after restarting; it does not automatically center.
A restart also restores the usual network/profile defaults. Face and speaker
remain operational with the servos unpowered. Mechanical gear resistance may remain.

## Drive mode from the face and speech panel

Run `./app faces`. **Load driving mode** in that same page opens the existing
LEGO driving window with the local Hugging Face ACT step-5000 checkpoint.
It restores powered head control, centers the camera at 0°/0°, and configures
320×240 at 10 FPS/Q85. Place the robot on the training track and center the
controller sticks before loading. The normal joystick mapping remains active.

Hold controller **R1**, or **Space** in the driving window, with neutral sticks for model driving, for up to 20 seconds
per hold. Release the held button/key to stop AI driving, or use the sticks/arrows to take over. Space works without a controller and stops controlling the model when the driving window loses focus. Hold L2/R2 to record a trial.
The panel reports model, LEGO, camera, and controller readiness. It does not start
autonomous motion merely by loading the model.

Face expressions, Stack Chan speech, and delayed MacBook speech remain available.
Head-position controls are blocked while driving owns the camera pose.
**Stop driving mode** closes the driver, stops its commands, releases servo power,
and restores the current expression. The threaded panel keeps Stop responsive
while speech is being prepared. Closing the driving window also stops the mode.
Closing only the browser tab does not stop the driver; use Stop or Q in the driving
window. If the panel process dies, its two-second lease expires and the driver
closes. The existing one-second LEGO watchdog remains independent.

Only one driving runtime can own LEGO at once. Logs and session status are saved
under `.local/panel-drive/`. The live-camera, motion-disabled smoke loaded the
actual checkpoint, exercised speech alongside inference, and verified lease-loss
shutdown. It does not establish track-following performance with the new panel.

## Try the trained model

```bash
./app run --policy
```

This loads the best road-v1 ACT checkpoint (step 5000) on the Mac. **Hold R1 or Space in the driving window**
with neutral driving sticks to let the model drive. Release R1 for manual
control; moving a driving stick takes over immediately, even while R1 is held.
Returning the sticks to neutral while still holding R1 resumes model control.
Each continuous R1 hold is limited to 20 seconds; release and hold again for
another trial. Manual control remains available without an arm/disarm step.
The camera centers at 0° / 0°, and motor strengths remain throttle 75% / steering 25%.

Inference reads each new latest image, with one request in flight and no queued
action chunks. Predictions must match the live stream and be less than 500 ms
old; model faults or stale predictions produce zero model commands while manual
control remains available. The camera must use the trained 320×240, 10 FPS,
JPEG Q85 profile. Predictions are clamped to the trained action range.
The 500 ms limit includes camera acquisition/encoding and inference latency;
at roughly 210 ms latency it leaves room for normal image intervals and brief
frame drops, without inserting stop commands between healthy predictions.

In inference mode, **R** starts/stops recording camera video and decisions. Clips go to
`.local/inference-recordings/<clip>/`: `video.mp4` (encoded after stopping), original
`frames/*.jpg`, and `events.jsonl` with predictions, selected actions, actual BLE writes,
and manual/model control modes. These recordings are tagged `training_eligible: false`;
the training exporter rejects them even if explicitly selected or copied into `data/`.
R records independently of Space/R1 and keeps recording across manual takeovers.
L2/R2 still record ordinary demonstrations when no policy is loaded.
Earlier trials remain in `.local/policy-trials/`; ongoing inference diagnostics are in
`.local/policy-runs/`. Trial behavior still needs testing on the physical track.

## Wireless camera setup

This prototype uses dedicated camera firmware, replacing the ER2 companion
application until restored. It keeps GC0308 acquisition running and streams
320×240 JPEG frames. Touch and microphone remain inactive; the speaker is initialized
before camera startup and later plays PCM through I2S without accessing camera I2C.
Pan/tilt uses the independent servo UART through an authenticated
control service on port 81; video remains on port 80.

The board uses **2.4 GHz Wi-Fi** on the same LAN as the Mac; the Mac may use 5 GHz or Ethernet. Enter credentials
using `python3 wifi_setup.py`, then open the localhost URL it prints. Settings
are stored in ignored `.local/wifi.json` with mode 0600, and are transferred over
USB into the device's NVS. They are never embedded in source. The private stream
key and endpoint live in `.local/camera.json`.

After flashing, configure and check:

```bash
uv run python configure_camera.py --port /dev/cu.usbmodem101
uv run python configure_camera.py --port /dev/cu.usbmodem101 --status
./app probe --camera-only --seconds 15
```

Build with `./firmware.sh build`, then `./firmware.sh flash`. This reuses the
pinned toolchain installed by the sibling Stack Chan ER2 example; it does not
edit that example. `STACKCHAN_TOOLCHAIN` can point at an equivalent installation.
The current device's full 16 MB restore image is kept privately at
`.local/stackchan-before-camera.bin`; flashing requires that backup to exist.
To install the D/B hub program: `uvx --from pybricksdev==2.3.2 pybricksdev run ble
--no-start hub/main.py` with the hub advertising.

Once configured, USB is unnecessary for camera/control communication. Unplugging
USB and confirming battery operation remains a distinct hardware check.

## Joystick samples paired with every image

SDL joystick input is polled on the UI thread at a target 120 Hz; rendering stays
at 30 Hz. Actual polling Hz is displayed and recorded. This is the host polling
rate, not a claim that the Bluetooth controller produces 120 new states per second.
The Stadia left vertical axis supplies throttle; the right horizontal axis supplies
steering. Camera input is always zero. Motor sending independently targets 10 Hz and
has no application command queue.

Each image gets the latest input sampled at or before its estimated capture
time. Unchanged input can be reused across images with its original sample
timestamp. Schema 7 frame events store `action` (the safety-gated requested
drive action), `joystick` (requested drive/head axes, sample time, age, source,
controller connection, focus/stop state, and connection availability), and
`last_ble_command` (the latest completed Bluetooth write at or before estimated
capture). These distinguish operator intent from transport delivery; they do
not measure wheel motion. Small bounded histories support recording alignment
only and are never replayed as motor commands. Missing or >250 ms-old input is
explicitly represented by `action: null` and `action_valid: false`.

Per-image pairing follows the actual received images, including gaps; it never
invents frames or claims the BLE motor-command rate matches camera FPS. Device/
host clock alignment remains estimated and includes unknown minimum network
delay. Original timestamps remain available for later export/alignment choices.

The 2026-09-26 ten-second motion-disabled test recorded 98 images with 98 valid
Stadia samples, zero missing input samples, median polling 115.22 Hz, and maximum
sample age 8.55 ms. Both throttle and steering varied in both directions; all
samples preceded estimated capture. Camera delivery averaged 9.94 FPS at fixed
10 FPS/Q85, with no missing sequences or reconnects. Test data is separate under
`.local/joystick-tests/20260926-122008-46eb012a`. No actuator commands were sent.

The motion-disabled background-input check on 2026-09-26 recorded 98 images with
98 valid Stadia samples, including 54 while the driving window was unfocused.
Input polling median was 115.11 Hz and maximum sample age was 8.83 ms. The sticks
were neutral during this check; background motion control remains an operator
check. Evidence: `.local/background-input-tests/20260926-125839-e778d4c0`.

Trigger input works in the background, independently of driving. Capture timestamps
exclude frames from before the hold and after release. Disconnecting the controller
ends the hold and saves the clip. The Stadia triggers use SDL's mapped trigger axes,
normalized to 0–1; recording starts at 20% travel. Each new hold creates a new folder.

## What gets recorded

`data/<episode>/episode.json` records task, result, power, D/B port mapping,
source revision, and timestamp conventions. `frames/*.jpg` contains the original
JPEGs. `events.jsonl` preserves:

- camera sequence, device capture/send clocks, host receipt clock, estimated
  capture time, added transport delay, and one paired joystick/action sample per image;
- startup zero-position head commands and servo feedback, when centering overlaps recording;
- normalized `[throttle, steer]` and calibrated `[left, right]` powers for every
  completed BLE write, with send start/ACK times, `transport_ack: true`, and
  `hub_consumed: false`; separate heartbeat reply timestamps.

The estimate aligns the camera clock using the smallest observed receipt minus
send offset. Its unknown minimum network delay remains an uncertainty; it is not
hardware clock synchronization. Bluetooth ACKs confirm transport acceptance,
not motor-command consumption or wheel movement. The periodic heartbeat confirms
the bridge is responding. Earlier events with `hub_consumed: true` used a
per-command PONG; historical metadata is retained. There is no invented
pose/velocity measurement.

```bash
./app inspect data/<episode>
```

These folders contain raw timestamped capture. The optional ACT workflow below
exports separate LeRobot datasets and keeps the raw files intact so alignment
choices can be revised without recollecting the data.

## ACT training

Training has its own `training/` uv project and lockfile. The driving environment
does not install or import PyTorch. The training tools never connect to the robot.

```bash
./app build-training
./app training prepare
./app training smoke --device mps --output .local/training/road-v1/local-smoke
./app training submit --stage smoke
```

The exporter selects completed `saved` driving clips, excludes the two initial
button tests, validates capture/action pairing, and retains the original files.
Whole clips are split with seed 42; gaps create separate contiguous learning
segments within the same split. RGB pixels are stored losslessly in LeRobot
image-backed Parquet at 10 FPS. The manifest retains original capture times,
controller sample times, frame hashes, source IDs, and the motor mapping.
No quality label is added to a recording.

The ACT input is `observation.images.stackchan` (320×240 RGB), with no informative
state input. The output is normalized `[throttle, steer]`, applied through the
same 75% throttle / 25% steering mapping during a later deployment. ACT predicts
10 actions; the configuration executes one action before observing again.
A device-only empty tensor handles LeRobot 0.6.1's internal state-device assumption
without exposing previous actions. Training statistics come only from training clips.

Cloud submission uses private repositories under `robium-admin` and the existing
HF login. Source, lockfile, and dataset revisions are pinned. A 200-step L4 smoke
has a 15-minute timeout. Download its checkpoint and verify it on the Mac before
the full run:

```bash
./app training fetch --stage smoke
./app training evaluate --checkpoint CHECKPOINT_DIR --device mps \
  --limit 16 --verify-smoke --output .local/training/road-v1/cloud-smoke-check
./app training submit --stage train
```

Full training uses batch 8, up to 20,000 steps, validation/checkpointing every
1,000 steps, and a four-hour job timeout. After step 5,000, five validations
without improvement end training. Checkpoints include weights, normalization
processors, optimizer state, and experiment metadata. The run ledger reserves
worst-case GPU cost before every allocation and enforces a $10 total ceiling.
Re-submitting a stage is refused to prevent duplicate paid jobs.
`--flavor` selects another GPU; the default L4 was available when the L40S was
queued. A retry requires a confirmed failed or canceled job and enough remaining
budget. An uncertain submission blocks allocation until it is resolved.

Offline reports include throttle/steering MAE, future-chunk MAE, a constant-action
baseline, shuffled-image sensitivity, reload verification, and prediction plots.
Local evaluation measures inference latency without sending motor commands.
Low offline error alone does not establish successful physical road following.
For a later dataset, use a new `--bundle` and `--repo-prefix` during preparation.

After the GPU job completes, download and evaluate its selected checkpoint:

```bash
./app training fetch --stage train
./app training evaluate --checkpoint CHECKPOINT_DIR --device mps \
  --output .local/training/road-v1/final-mac-evaluation
```

`fetch` prints the checkpoint directory. The first experiment's evidence is
recorded in [training-results.md](docs/training-results.md).

## Stop behavior

The BLE loop independently targets 10 Hz. Host input expires after 250 ms;
camera receipt expires after 500 ms. Camera loss temporarily stops motion; the preview keeps
reconnecting. LEGO and pan/tilt failures are isolated and never terminate video. The hub independently brakes after one second without a
valid complete command. The physical hub button stops its
program. The app reconnects LEGO automatically after a connection fault. Fresh
input resumes when connections recover; no E key or persistent stop latch exists.

LEGO connects directly to the Mac's Bluetooth adapter; Stack Chan carries only
video and head control over Wi-Fi. Drive commands are open-loop at the application
level: each cycle samples the latest joystick state and sends a three-byte `D`
packet, without requesting or waiting for a per-command PONG. A PING byte is included in the next control write when 250 ms have elapsed
since the last request. PONG replies are observed independently; no heartbeat
reply for one second stops driving and closes the BLE link before automatic reconnect. The deadline is
checked even while a GATT write is waiting for its transport acknowledgment.
The one-second motor watchdog and host/input timeouts remain active.

There is no application command queue or replay of missed control updates. Only
one GATT write can be in flight, and intermediate joystick values are replaced
by the newest input. This avoids queuing old motion in CoreBluetooth. Pybricks'
Command/Event characteristic requires write-with-response; transport ACKs and
the firmware's underlying receive storage remain, while per-command application
confirmation is removed. Slow transport ACKs can still reduce the actual rate.
The driving window shows actual write Hz, ACK p95 latency, and heartbeat age.
`uv run python benchmark_ble.py --seconds 120` tests this production loop using
zero motor power only, while the camera viewer can remain running. Results stay
under `.local/ble-tests/` and do not create or label training recordings.

Pybricks shuts down after idle time only when disconnected with no running
program ([official guidance](https://pybricks.com/learn/getting-started/pybricks-environment/)).
The bridge brakes after one second without a complete drive command. Separately,
a five-second timer without a valid drive command or PING ends the bridge program,
leaving the hub powered on for reconnection. Idle exit also applies if a program
is accidentally started from the hub button. Incomplete packets expire after
250 ms; stdin is read one available byte at a time, so a partial packet cannot
block braking or session cleanup. PING keeps the session alive but never keeps
old motor power running. Mac shutdown bounds the zero/EXIT attempt to 750 ms,
then attempts Bluetooth disconnect with a two-second deadline even if the stop
write stalls. There is no arm/disarm state; healthy connections enable current input automatically.

Pybricks distinguishes blinking blue (ready, program stopped) from fading blue
(program running), and Bluetooth is enabled by default
([official LED and program guidance](https://pybricks.com/learn/getting-started/pybricks-environment/)).
A 2026-09-26 zero-power hardware test deliberately disconnected without EXIT,
observed advertising after the idle timeout, then reconnected and confirmed
READY/PONG without a reset. Clean shutdown also returned the hub to advertising.
Evidence: `.local/ble-tests/20260926-123602-idle-recovery/report.json`. The LED alone
cannot establish whether the Mac can discover the hub.

Measured 2026-09-26 on Pybricks 4.0.1/profile 1.5.0: the previous loop with
per-command confirmation confirmed
934 zero-power commands over two minutes with the 10 FPS/Q85 camera active,
averaging 7.77 Hz, with zero BUSY errors/disconnects and three >300 ms replies
that recovered stopped. Pausing video gave 7.72 Hz; switching Mac Wi-Fi off
gave 8.28 Hz. None met the 10 Hz criterion. Wi-Fi-off reply p95 improved from
180 to 121 ms, but this does not isolate the remaining Bluetooth latency or
prove stability while driving. Direct AP and Ethernet were restored afterward.
Those historical tests used the previous 400 ms hub watchdog. Diagnostic comparison:
`.local/ble-tests/comparison.json`.

A LEGO write acknowledgment taking over 300 ms is now diagnostic only. It does
not stop driving, send an extra zero command, or end the recording. Once
the pending write finishes, the next cycle sends the latest joystick input.
Missing heartbeat replies for one second stop driving. Explicit transport errors,
BUSY rejection and input/video loss temporarily stop motion. Operator stop is
momentary on gamepad A; background gamepad input is unaffected by window focus. The independent
one-second hub command watchdog is aligned with the heartbeat deadline; a
command gap shorter than one second does not trigger that watchdog. Video remains available.
Connection errors are saved in `.local/runtime.log`.
A 45-second zero-power check with the camera active completed 333 writes at
7.41 Hz, including five >300 ms ACKs, without interruptions. All 126 heartbeat
replies arrived; maximum heartbeat gap was 541 ms. This validates tolerance of
slow ACKs, while the separate 10 Hz throughput criterion remains unmet. Evidence:
`.local/ble-tests/20260926-123133-open-loop-10hz/report.json`.
Camera centering retries network failures up to three times at startup. It sends
only a 0° / 0° target, verifies servo feedback, then holds and closes the control
connection. No recurring head requests or joystick camera controls remain. Video
continues if centering fails; driving waits for startup centering to succeed.

## Provenance and current limits

Reuses the MIT LEGO BLE protocol and gamepad adapter and Stack Chan camera pin
configuration from `robium-ai/robium-apps` revision
`99166a1ce755edbff30d956e0e441a071ea06c9a`. The mBot recording example informed
the action convention and explicit episode labels. Upstream examples are kept
unchanged. Espressif's official CameraWebServer demonstrates the multipart MJPEG
transport used here. Firmware dependencies match Stack Chan ER2: ESP32 Arduino
3.3.11, StackChan-BSP 1.1.0, M5Unified 0.2.20, ArduinoJson 7.4.3.

See `docs/architecture-brief.md` for the scope and measured evidence. This is
the hardware/data proof, before hero-app design or training.

Video delays also stop driving and reconnect the stream automatically. Gaps and
stream generations are preserved in recordings; interrupted demonstrations are
not labeled successful. Video reconnects indefinitely with a bounded 0.5–3 second backoff until the app closes.

Pybricks `BUSY 0x81` during driving means the hub's stdin buffer cannot accept
another packet. The host temporarily pauses command sending and attempts only
zero-power writes up to three times. A bridge PONG confirms recovery, then the
next cycle uses fresh controller input; a
rejected motion packet is never replayed or logged as an accepted action.
Persistent busy errors trigger automatic BLE reconnection; camera streaming continues. Hub stdout and program-stop status are
now captured in `.local/runtime.log` to distinguish a stopped/crashed bridge
from transient backpressure.


## Camera timing and collection quality

Firmware 0.4.4 uses an independent encoder task at a nominal 8 FPS and holds only
the latest encoded JPEG. TCP sending cannot block acquisition/encoding. A slow
receiver can miss encoded sequences; this is counted instead of hiding delay in
an ever-growing frame queue. TCP_NODELAY avoids aggregation of small multipart
writes; multipart headers and each JPEG are sent together in one HTTP chunk.
The applied socket option and Wi-Fi power-save mode are exposed for verification.
Default profile: 320×240, software JPEG quality 75. No adaptive resolution
or compression, duplicated frames, or synthetic padding is used.

The live five-second metrics show received FPS, FPS from timestamps of received
captures, frame age, p95 delivery interval, >250 ms gaps, missing encoded stream
sequences, reconnects, stale frames, encoder/send durations, and missed producer
slots. Missing stream sequences are NOT sensor-driver drops: CAMERA_GRAB_LATEST
can skip sensor frames before encoding, and those drops are unknown. Frame age
is host receipt age, not calibrated end-to-end capture latency. Images retained
after a lost stream are visibly dimmed and labeled NO LIVE VIDEO.

Schema 7 stores per-image joystick/action pairing, profile, and timing telemetry.
Older recordings retain their original schema. Camera timing never
changes an operator-selected recording label or adds a quality label. Explicit
benchmarks produce their own timing reports separately from training recordings.
`inspect` can display timing measurements without changing saved metadata.
Camera-only recordings retain gaps for diagnosis. Driving interruptions end the
driving episode. Recorder queue overflow invalidates recording but keeps video.

Direct Wi-Fi removes the home-router path, but must be measured before claiming
an improvement; it does not remove software encoding cost or radio contention.
Firmware 0.4.4 supports an explicit, password-protected AP-only experiment at
192.168.4.1. Reset always returns the device to its saved home Wi-Fi; home
credentials and the stream key are retained. An optional lease bounds offline
tests. Ethernet-backed sessions can remain in AP mode until reset or an explicit
return to station mode.


## Explicit camera collection benchmark

Stop the viewer before running a benchmark (the firmware services one stream).
`uv run python benchmark_camera.py --seconds 300 --name 8fps-q75-baseline`
collects and decodes every JPEG, writes real images and timestamps under the
ignored `.local/benchmarks/`, and reports mean and ten-second-window FPS,
missing encoded sequences, stale frames, reconnects, capture/delivery intervals,
encode/send timing, and payload bandwidth. This does not mark user recordings.
Capture cadence and received-frame delivery jitter are reported separately;
small arrival jitter does not imply a frame was lost from collected data.

Firmware exposes authenticated, temporary benchmark settings at
`http://DEVICE:81/camera`: GET reports the current profile, Wi-Fi signal and
association-disconnect counters, boot ID and heap; POST accepts integer
`fps` (2–10) and JPEG `quality` (35–85). Settings stay fixed during a trial and
return to 8 FPS/Q75 on reboot. This endpoint never moves the head or the LEGO.
Per-frame headers carry the actual FPS/quality and Wi-Fi diagnostics.

Use `uv run python benchmark_camera.py --seconds 300 --fps 8 --quality 55
--name 8fps-q55` to test stronger compression at the same FPS, then compare
`--fps 6 --quality 55` if needed. Each benchmark uses one stream, collects and
decodes actual JPEGs, and produces its own report. `--throughput` runs three
4 MiB bulk transfers on an authenticated diagnostic endpoint with the encoder
still active; this measures available bulk throughput, not guaranteed image
latency. Keep the scene, robot position and network fixed for comparisons.

Measured on 2026-09-26: earlier five-minute 8/Q75, 8/Q55 and 6/Q55 trials
had long pauses. After the v0.4.3 transport update, a five-minute camera-only
8/Q75 trial collected 2399 valid images (7.997 FPS), with no observed missing
sequences, retries or stale frames; longest delivery gap was 268 ms. It passed
the explicit collection criteria but not the stricter delivery-jitter check.
The scene/position changed and final JPEGs were smaller, so this establishes a
pass for the tested conditions, not a controlled proof of the cause or full
driving stability. Details are in `docs/architecture-brief.md`; local reports
are in `.local/benchmarks/comparison.json`.

## Direct Wi-Fi with Ethernet internet

Keep USB attached for the initial mode change and recovery; images still travel
over Wi-Fi. Stop the viewer before testing. On macOS, put the active Ethernet
service ahead of Wi-Fi in network service order and verify internet through it.
The direct test verifies the requested default internet route and HTTPS before
and after joining Stack Chan's Wi-Fi.

`uv run python -m lego_stackchan_drive.direct_wifi --run --baseline
--internet-interface en7 --stay --seconds 300` collects a five-minute home-router
baseline and a five-minute direct-AP trial at 8 FPS/Q75, then keeps direct Wi-Fi
connected. Change en7 to the actual Ethernet interface. Leave camera position,
scene and lighting fixed. Reports are separate from operator recordings.
Ethernet remains the internet route; the camera uses 192.168.4.1 over Wi-Fi.
Generated AP credentials stay in the private `.local/direct-wifi.json` file.

A detached recovery process starts before the network change. Failure restores
Mac home Wi-Fi, device station mode and the private camera configuration. A
completed `--stay` trial cancels recovery; its state remains under
`.local/direct-wifi-tests/`. To return to home Wi-Fi, use
`uv run python -m lego_stackchan_drive.direct_wifi --session SESSION_PATH
--restore-after 0`. The original Mac service order is saved separately in
`.local/network-order-before-direct-wifi.json`; Ethernet priority remains as
requested. Opening this board's USB status port was observed to restart it, so
tests use authenticated HTTP status after the mode change and avoid USB polling
during collection.

The 2026-09-26 direct-link test collected 2400 images in five minutes, exactly
8 FPS in every ten-second window, with no observed missing sequences/retries or
stale frames. Longest delivery gap was 182 ms; both collection and timing checks
passed. Direct bulk throughput was 5.34–5.42 Mbps with encoding active, versus
0.625 Mbps image payload. Internet remained on Ethernet. This is camera-only
evidence; driving and head-control workloads still need validation. Local
results: `.local/benchmarks/direct-wifi-comparison.json`.

The selected session profile is now **320×240, 10 FPS, JPEG quality 85**.
Its five-minute direct-Wi-Fi trial collected 2997 images (9.99 FPS), with one
observed missing encoded image and no reconnects or stale frames. The operator
accepted 1–2 missing images; the original stricter benchmark report is retained.
The camera-only preview uses this fixed profile, with internet through Ethernet.
These runtime settings return to 8 FPS/Q75 and saved home Wi-Fi after a reset.

## LCD emotions

Run `./app faces` and open its local URL to test **neutral, happy, angry, sad,
doubtful and sleepy** on Stack Chan. The panel uses the existing private camera
configuration; it never connects to LEGO or loads a driving model. Select an
emotion, cycle all six, or enter text and press **Speak on Stack Chan**. Faces
blink and move their eyes on screen; the physical head starts straight at 0°,0°.
The preview is a board-rendered snapshot, refreshed on selection or manually,
so it does not compete with camera streaming as another live video feed.

Firmware 0.5.0 adds authenticated HTTP actions on port 81:

```json
{"emotion": "happy", "talking": false, "auto_cycle": false, "animated": true}
```

Send any nonempty subset to `POST /face`, using the existing `X-Stream-Key`.
Selecting an emotion stops cycling unless the action explicitly enables it.
`GET /face` returns commanded and visible emotions, render counters and readiness.
`revision` identifies the latest accepted action and `rendered_revision` identifies
the action that has reached the LCD. The test panel waits for these to match before
requesting its preview.

`GET /face.bmp` returns the current 320×240 LCD canvas. Unknown fields and invalid
values return 400 without applying part of an action. Face commands persist until
changed or rebooted. Closing the panel leaves the LCD animating. Wi-Fi loss leaves
the face running, and the panel reconnects when the device is reachable again.

Future race and ER2 modes can call `FaceClient.send(emotion="happy")` without
owning the renderer. The LCD task uses SPI below camera priority and never
accesses the camera's internal I²C bus.

### Audio-driven speech (firmware 0.6.5)

Speaker master volume is set to its maximum, 255/255, for filming.
`GET /speech` reports `volume` and `volume_max`.

The panel now defaults to local neural **Kokoro-82M v1.0 int8**, with **am_puck** at
1.03× speed, matching `stackchan-er2-sim` and `silly-turtlebot`. The model runs on
the Mac; Stack Chan receives audio rather than running the model on its ESP32.
The picker has 28 American/British English Kokoro voices and a separate group of
installed macOS system voices, including Samantha and Zarvox. Names beginning
`kokoro:` select neural speech; other allowlisted names use `say` and `ffmpeg`.
Calls without a voice now use `kokoro:am_puck`.

Install the locked runtime and checksum-verified model assets once, then open the panel:

```bash
./app build
./app build-voices
./app faces
```

`build-voices` downloads the pinned model and voice files into ignored
`.local/models/` (about 115 MB combined); verified existing files are reused.
An optional `--reuse /path/to/existing/models` copies matching cached files.
The [Kokoro ONNX runtime](https://github.com/thewh1teagle/kokoro-onnx) is MIT;
Kokoro model weights are Apache 2.0. Speech works without Internet after setup.
The first Speak loads the model, and each clip is synthesized before upload;
this is a phrase-at-a-time test, not streaming TTS. The panel limits text to
120 characters and clips to 20 seconds. Neural PCM is checked for sample rate,
finite values and duration, clipped safely to signed 16-bit, and padded with
200 ms leading and 300 ms trailing silence.

Generated audio is uploaded to the board speaker. Five rounded audio bars permanently replace
the mouth, centered below the eyes. The glyph is 64 pixels wide with 8-pixel bars,
twice its original width; the tallest bar reaches 72 pixels, twice its original
peak height. Every bar uses the same 12–72 pixel height range, so position
does not bias the visualization. Their heights follow broad
low-to-high frequency energy from the same PCM, with smoothing and a silence
gate. During pauses and after playback, the bars settle to resting heights of
12 pixels and remain visible. Emotions still change the eyes and decorations.
The browser preview remains a snapshot; watch the
physical LCD to see the animation.

`FaceClient.speak_pcm(pcm)` accepts mono 24 kHz signed 16-bit little-endian PCM,
up to 20 seconds per clip. It sends authenticated `POST /speech` on port 81 with
`Content-Type: application/octet-stream`. `GET /speech` reports playback phase,
position, `audio_bands`, `displayed_audio_bands`, `audio_level` and rendered
voiced/silent frame counts. The original `mouth_open` fields remain compatibility
aliases for audio activity; they do not describe lip shapes in this firmware.
Busy uploads are
rejected with 409; speech has no pending clip queue. Future ER2 output can use this
PCM boundary; ER2 listening/conversation and a mode switcher are not implemented.
See [speech reference notes](docs/speech-references.md) for the inspected
Silly TurtleBot audio/ER2 boundaries and the intended future conversation mode.

The animation uses a local scheduled PCM clock with an approximately 21 ms DMA
offset; the speaker API exposes no DAC sample feedback. A small overlapping
filter bank with boundaries at 200, 500, 1200 and 3000 Hz supplies the five bars;
this is a broad audio visualization, not a calibrated FFT spectrum.
The audio renderer targets 20 FPS while speaking, with less frequent gaze redraws;
idle face animation targets 8 FPS. These are caps, not guaranteed measured rates.
Amplifier initialization happens once before the camera claims I²C; playback then
uses only the initialized I2S driver. The physical head stays at 0°,0°.

The earlier 0.6.0 mouth-animation 30-second direct-Wi-Fi check collected 297 valid images
(9.9 FPS) at 320×240/Q85, with no missing encoded sequences, reconnects, stale
frames or source missed slots. Longest sensor interval was 200 ms and longest
delivery gap was 182 ms; the collection criteria passed. Mouth redraws measured
11.9–12.6 FPS across three clips, with voiced and silent frames and a closed
mouth on completion. These are short concurrent bench results, not a driving
test or a microphone measurement of perceived synchronization. Private evidence
is under `.local/speech-tests/`; the previous 0.5.0 firmware is backed up under
`.local/firmware-backups/0.5.0-before-audio/`.

The 0.6.1 spectrum update passed a 20-second concurrent camera/speech check:
198 valid Q85 images (9.9 FPS), no missing sequences, reconnects or stale frames,
and a maximum sensor interval of 199 ms. Two speech clips rendered 44 and 64
audio frames over 5.802 seconds each (7.6 and 11.0 FPS under camera load).
A physical-board tone test confirmed predominantly low bars for 100 Hz and high
bars for 4 kHz, with zero levels on completion. Board-rendered snapshots verify
the glyph's placement and the restored normal mouth; they are canvas snapshots,
not photographs of the LCD. Evidence is under `.local/spectrum-tests/`.
