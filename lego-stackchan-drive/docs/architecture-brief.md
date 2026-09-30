# Driving and capture proof

Outcome: operator drives a real D/B LEGO differential-drive robot with a Stadia
controller while a mounted Stack Chan sends camera images wirelessly to the Mac.
Record timestamped demonstrations, then train and evaluate a first image-only
ACT policy for the same circuit before designing the final app.

Chosen path: reuse selected pieces from LEGO Powered Up teleop and Stack Chan
ER2; use mBot's normalized two-action convention. Holding L2/R2 records;
releasing both saves without a success/rejection label.
Native Python/uv/Pygame/Bleak on macOS arm64. Separate camera and BLE threads;
storage stays in the UI thread so a storage stall expires motor input.

The camera now uses persistent GC0308 acquisition, JPEG quality 85, and a
10 FPS Wi-Fi multipart stream. The Mac connects to Stack Chan's access point
and uses Ethernet for Internet access. The original per-photo USB firmware
measured 1.94 FPS over eight frames. No ROS or model API is needed for capture.

Current driving: automatic availability, background controller input, expiring
input, camera freshness checks, heartbeat timeout, and independent one-second
hub watchdog. There is no manual arming, Space pause, or A-button stop. Real zero
commands and READY/PONG passed after replacing A/B with D/B. The left/right
mapping is left port D and right port B. Current controls use left-stick Y for
75% throttle and right-stick X for 25% steering, with camera pan/tilt fixed at 0,0.

Data: immutable raw JPEG frames, device/host clocks, transmitted wheel commands,
task, calibration, episode outcome, and source revision. The camera clock estimate
includes unknown minimum network delay. No motor feedback is currently recorded.
Offline training is isolated in `training/`, with pinned LeRobot 0.6.1 and a
separate uv lockfile. Export stores lossless image-backed 10 FPS datasets and
preserves raw capture/action timestamps in the manifest. Whole source clips
stay together when splitting; capture gaps split only their learning segments.
ACT sees the image and predicts normalized throttle/steering, without previous
action input. A 200-step private HF Jobs smoke precedes a bounded 20,000-step
run, with a $10 allocation ceiling. Real policy driving remains separate.

Training proof completed: the L4 run stopped at 10,000 steps and selected step
5,000. Held-out steering MAE is 0.152 versus 0.489 for a constant-action baseline.
The same downloaded checkpoint passed all 856 validation frames on Mac MPS with
about 9 ms inference. Estimated total GPU compute is $0.63; raw recordings remain
unchanged. See [training-results.md](training-results.md) for limits and artifacts.

Acceptance: prove sustained Wi-Fi frames, inspect the real view, record and reopen
a combined zero-power hardware episode, then have the operator drive a short
bounded demonstration and verify nonzero command/frame alignment. Finally unplug
USB to establish that power and connectivity work untethered. Only demonstrated
items should be reported as working.

## Evidence from this session

- Stadia controller detected: six axes and 17 buttons.
- Existing Stack Chan camera: eight valid 320×240 JPEGs, 1.94 FPS; actual image
  inspected and currently points upward rather than at a road.
- Initial LEGO failure diagnosed from hub stdout as ENODEV at left motor
  initialization. Changed left port A to D, kept right B, downloaded the program,
  and passed real zero-power READY plus PING/PONG. No nonzero wheel command sent.
- Six focused host checks pass, covering stale UI, stale camera, BLE failure,
  shutdown, timestamp storage, and empty recording rejection.
- Dedicated Wi-Fi firmware compiled and flashed with hash verification. A
  first-boot network initialization fault was diagnosed and fixed; real USB
  status now reports `stackchan-camera`, `camera_ready: true`, and no Wi-Fi
  connection. Full pre-change 16 MB flash saved privately for restoration.
- Wireless throughput, combined episode recording, physical motor direction,
  actual operator driving, and USB-unplugged battery operation remain unverified.
  Wi-Fi setup page awaits local credential entry; LEGO hub needs powering on again.

## Wireless verification

Wi-Fi provisioned locally and camera connected on the LAN. A 15-second combined
zero-power probe saved and reopened `data/20260925-190952-0aa1c710`: 141 camera
frames at 9.62 FPS, maximum frame gap 248 ms, and 52 completed BLE commands
after connection startup. Measured command rate 8.10 Hz, maximum gap 180 ms,
mean acknowledged write 123 ms. All wheel commands were zero. The nominal
control target is 10 Hz; actual transport timestamps remain authoritative.
A saved image was visually inspected: real room content, still pointing upward.
The driving UI was launched at 25% maximum power, initially disarmed. Physical
direction, operator demonstration, and USB-unplugged operation remain pending.

## Two-stick control update

The operator requested left-stick XY driving and right-stick XY camera aiming.
Driving retains the operator-corrected throttle +1 / steering -1 calibration.
Camera aiming runs independently while the window has focus, including with
wheel driving disarmed. Firmware 0.2.0 adds authenticated pan/tilt on HTTP port
81, separate from the blocking video stream on port 80. The UART servo interface
does not use the camera's shared I2C pins. Bounds are yaw ±45°, pitch 5–85°,
target rate 25°/second, and 300 ms onboard command expiry. Release stops the
animation at the current servo position; focus loss and Space/gamepad A also stop.

15 host tests pass, including independent stick routing, all-axis stop, and
head-command expiry. Real head/video smoke passed: pan changed 0.3°→4.0° and
pitch 43.1°→47.1°, then held after command expiry (pan 4.0°→4.0°, pitch
47.1°→46.8°). Invalid input was rejected with HTTP 400. Concurrent video delivered
47 frames at 9.51 FPS. No wheel motion was commanded by the smoke test.

Episode schema 2 keeps the two driving actions and adds timestamped head actions
and servo-angle feedback; it does not silently reinterpret camera movement as
driving. Aim before road-following demonstrations when training a fixed-view
driving policy. Training a policy that also controls gaze remains a later choice.

The subsequent combined capture saved 129 camera frames and 142 head samples,
but the hub had stopped advertising, so that episode is marked interrupted and
contains no wheel commands. Reconnection awaits the operator powering the hub on.

After the operator powered the hub back on, the integrated zero-power capture
passed: `data/20260925-191714-7db2f15a` contains 183 frames at 9.23 FPS,
91 completed wheel commands (all zero), and 190 head-control samples. Maximum
camera gap was 274 ms. All JPEGs reopened successfully. Updated UI relaunched
with wheel driving disarmed and the left-drive/right-camera mapping.

## Reproduced Bluetooth timeout

A stationary combined diagnostic reproduced `LEGO Bluetooth: TimeoutError` on
2026-09-25. Normal acknowledged wheel writes averaged about 126 ms and often
reached 181 ms; the original hard 300 ms cancellation eventually fired and
stopped all workers. Both Wi-Fi endpoints remained responsive independently.
This establishes one timeout cause without assuming every past timeout was the
same. [Pybricks requires acknowledged writes](https://github.com/pybricks/technical-info/blob/master/pybricks-ble-profile.md#profile-v120),
so unacknowledged streaming is not a supported fix for this characteristic.

The host now shields an in-flight BLE write from premature cancellation, disarms
at 300 ms, allows up to 1.5 s total to settle, and confirms zero before marking
the link ready. It never automatically rearms or replays the previous motion.
The hub's independent 400 ms watchdog is unchanged. Errors retain their first
connection-specific cause and are persisted locally. Joystick refresh cannot
overwrite a concurrent worker disarm. Moving episodes are interrupted on slow
ACK recovery. Regression checks cover a slow acknowledgment (uncanceled write,
confirmed zero, no rearm) and a permanently hung write (bounded failure).

A subsequent stopped test also reproduced `Camera pan/tilt: timed out` with the
original 400 ms HTTP response deadline. Head transport now allows 1.5 s for a
reply, detects slow responses over 300 ms, and recovers using only zero commands
on a fresh connection (three bounded attempts). The firmware still expires head
motion at 300 ms independently. A neutral-stick latch prevents a held right stick
from restarting motion when the connection recovers. Wheel driving is disarmed
and affected episodes are interrupted. No firmware or watchdog extension was needed.

The next diagnostic caught a camera backlog exceeding 350 ms alongside head
latency. Video now closes the stale stream, clears its freshness timestamp,
disarms, and reconnects with a new stream-generation marker. It records an
explicit camera-gap event and interrupts the episode; three consecutive failed
reconnects still fail loudly. Ten valid frames clear the consecutive failure
count. Recovery does not automatically rearm wheels or bypass neutral head input.
The regression suite now has 20 passing checks, including video reconnection.

The complete recovery build passed a 60-second zero-power hardware diagnostic:
`data/20260925-193151-7e4ddbc2`, 477 frames (~7.98 FPS), 419 acknowledged wheel
commands, and 500 head samples. It recovered four video gaps and five head delays
without terminating the session; longest camera gap including reconnection was
4.53 seconds. All wheel commands were zero. This validates stopped recovery,
not stable wireless driving or demonstration quality. The UI was relaunched
at 25% power, disarmed. Wireless intermittency remains a collection limitation.

## Absolute camera stick control

Firmware 0.3.0 changes pan/tilt from velocity to absolute position as requested:
yaw = 45 × right-stick X, pitch = clamp(85 × up input, 0, 85), in degrees.
Centered input targets physical (0, 0); down cannot command negative tilt.
Holding the stick does not accumulate rotation. Targets use the existing smooth
servo motion at speed 400. Explicit `hold` is separate from zero position:
Space/A, lost focus, expired commands, and recovery hold the current pose.
The independent 300 ms device watchdog remains. A protocol capability check sends
only hold before allowing absolute commands, preventing new host input from
silently becoming velocity commands on older firmware. Schema 3 records this
mapping and the device's explicit command mode.

22 host checks pass. Firmware built and flashed with hash verification. During
real video capture, a fixed (9°, 12.75°) target held at reported (6.8°, 11.2°)
across repeated commands; the initial 2° precision assertion was too tight for
the observed 2.2° yaw error. A down command stayed at the zero-tilt end (reported
1.5°), and release settled at (0.6°, 1.5°), within 3° of requested center.
The return/down test streamed 37 frames at 8.53 FPS. This verifies position and
release semantics, without claiming sub-degree servo accuracy.

## LEGO BUSY 0x81 follow-up

The operator reported GATT 129 while using the sticks. Pybricks defines this as
BUSY; its WRITE_STDIN handler returns it when the input ring has insufficient
free bytes. This does not establish whether the bridge crashed, stopped, or
stalled. The former client discarded all unexpected stdout and status reports.
The client now preserves diagnostics and detects a bridge program stopping.
BUSY during a drive write disarms, marks an interruption, and retries only zero
power at most three times. A PONG is required before restoring ready; rearming
remains manual. Attempted rejected actions are recorded separately from commands.
Other GATT errors remain fatal. No hub firmware or camera mapping changed.

25 host checks pass, including transient/persistent BUSY, no motion replay,
PONG gating, exact error-code classification, and stopped-bridge diagnostics.
A 45-second concurrent hardware probe `data/20260925-194346-795ad0de` captured
397 frames (8.87 FPS), 299 zero-power writes and 377 head samples, recovering
one video/head delay (maximum frame gap 1.13 s). No LEGO BUSY occurred.
The program-stop log at the end of this probe was its expected EXIT; logging
now distinguishes requested shutdown from unexpected program termination.
This does not reproduce or resolve the underlying driving-only buffer buildup;
new diagnostics are needed on the next operator run.

## Independent camera and measured timing (2026-09-26)

Camera preview/reconnection is now independent of BLE and pan/tilt failures.
Only explicit shutdown sets the shared stop event. Separate component errors
disarm affected controls without terminating the camera. Video retries continue
with bounded backoff; stale frames are logged but excluded from live control.
Sustained backlog triggers reconnection after two seconds, rather than tearing
down a stream on the first late frame. Frozen preview is dimmed and labeled.
`--video-only` isolates video with no BLE/head traffic; `--camera-only` retains
absolute head aiming. Both can record independent camera diagnostics with R/F.
Driving recordings still end on control faults. Schema 4 records camera profile,
encoder/capture-wait/previous-send duration, boot ID, sequence, source missed slots,
and timing acceptance reasons. Failed timing is never saved as success.

The unpaced v0.3 video-only 60-second baseline was
`data/20260926-104113-c7a8b0c4`: 430 frames, 7.187 FPS, max gap 361 ms,
p95 gap 259 ms, no sequence gaps/reconnects. An earlier 20-second run overlapped
a USB status query and is not a clean network/camera performance baseline.

v0.4.0 added telemetry and paced the serial encode/send loop. The 60-second
`data/20260926-104304-f12c5b86` diagnostic measured 7.076 FPS, JPEG encode p95
81.8 ms, previous TCP send p95 127.9 ms, and 54 missed scheduling slots. This
identified sequential encode/send as a throughput limitation.

Installed v0.4.1 separates encoding from network transmission. An 8 FPS encoder
task publishes a single newest JPEG; the sender copies it under a mutex before
sending, so network writes do not hold the producer lock or own shared buffers.
Skipped encoded frames create visible sequence gaps. No queue of stale images
can accumulate on the device. TCP_NODELAY is requested for the multipart stream.
Resolution remains QVGA, software JPEG Q75; no automatic quality reduction.

The v0.4.1 video-only 60-second check `data/20260926-104559-acfd300c` produced
477 decodable 320x240 frames: 7.988 received FPS, 7.973 FPS from received sensor
capture timestamps, p95 capture interval 150 ms, p95 arrival interval 212 ms,
max arrival gap 269 ms. No encoded sequences were missing, no producer slots
were missed, no stale frames or reconnects occurred. Encode p95 was 83.4 ms,
previous TCP send p95 114.1 ms. Home Wi-Fi arrival jitter still fails the strict
provisional collection timing thresholds; this is an improvement, not a claim
that the wireless channel is constant. Sensor-driver skips remain unknown.

35 host tests pass; firmware compiled and flashed with hash verification.
Direct SoftAP remains an untested alternative: it removes the home-router path,
but shares device resources and does not eliminate RF contention or encoding.
No Mac Wi-Fi switch or new AP credentials were introduced.

The 60-second independence test `data/20260926-104707-c79a03ba` deliberately
selected an absent LEGO hub while streaming and issuing only head-hold commands.
313 camera frames arrived after the actual BLE discovery failure, proving
failure isolation on live video. The mixed workload was NOT stable: 358 frames,
5.988 received FPS, 20 missing encoded sequences, three stream interruptions,
four stale frames, and a 10.5-second maximum gap. Head requests timed out and
ultimately disabled the head worker; video recovered independently. This does
not isolate whether Wi-Fi contention or another device resource caused the
mixed-workload fault. The viewer is left in video-only mode to keep the current
step focused on camera transport. Do not claim production-ready collection.

## Explicit reliability trials; operator labels preserved (2026-09-26)

At the operator's request, Episode.close no longer computes/stores a camera
quality classification or rewrites success to needs_review. Labels stay as the
operator chose them. Camera timing measurements remain in raw events; explicit
benchmark results are separate. No existing recording had needs_review when
this correction was applied. Control-fault interruption handling remains.

`benchmark_camera.py` exercises actual collection: it stores every JPEG,
decodes each image to verify 320x240 content, and measures FPS in the entire test
window plus each ten-second subwindow. Its collection criteria distinguish
received jitter from losses: mean >=95% of target, every 10-second window >=90%
of target, no observed missing sequences/retries/stale/source missed slots,
maximum capture gap <=2.1 target periods and arrival gap <=500 ms. These criteria
apply only to explicit tests, never labels on user recordings.

A five-minute 8 FPS/Q75 v0.4.1 trial
`.local/benchmarks/20260926-105106-8fps-q75-baseline` collected 2250 decodable
images (7.50 FPS). Minimum 10-second rate was 4.6 FPS; 41 encoded sequences were
observably missing, four stream retries occurred, seven stale frames arrived,
and max arrival gap was 7.36 seconds. No producer slots were missed and there
was only one observed device boot ID. JPEGs averaged 14.6 KB; required image
payload at target 8 FPS is ~0.94 Mbps. JPEG encode p95 was 84.1 ms and previous
send p95 132.0 ms. This fails the sustained collection test.

Installed v0.4.2 adds temporary authenticated FPS/quality profile selection,
per-frame Wi-Fi signal and association-disconnect counters, and a separate
4 MiB bulk-throughput endpoint. Capture/streaming scheduling is unchanged from
v0.4.1. Bulk tests still include the encoder's CPU load. A first request during
post-flash startup was refused; ready-checked trials are used for comparisons.
Three complete 4 MiB transfers took 16.26, 16.46 and 16.19 seconds (2.064,
2.039 and 2.073 Mbps). Device status showed -53 dBm signal, zero association
disconnects, and ~146 KB free / ~120 KB minimum heap. These are bulk throughput
measurements, not proof of constant per-image latency.

Two additional five-minute v0.4.2 trials also failed the collection criteria:
8 FPS/Q55 collected 2197 images (7.323 FPS), with 72 observed missing sequences,
four retries, 12 stale images and a 6.45-second maximum arrival gap. Its mean
JPEG size was 10.7 KB, approximately 27% smaller than the first Q75 trial.
6 FPS/Q55 collected 1647 images (5.49 FPS), with 25 observed missing sequences,
five retries, 11 stale images and a 20.95-second maximum arrival gap. Neither
trial missed scheduled encoder slots or observed an association disconnect or
device reboot. Sensor timestamps were unique for every collected image in all
three trials. Missing-sequence counts do not include unobservable loss across
reconnections; effective collection FPS includes the entire test window.

The camera scene/position changed during testing: the later 6 FPS frames show a
hand near the camera and a laptop rather than the initial tabletop, and RSSI
fell to -70 dBm (median -56). These are tests under actual conditions, not
strictly controlled comparisons attributing changes solely to FPS/compression.
The results do not establish a reliable lower-rate profile.

Installed v0.4.3 sends the multipart header and JPEG in a single HTTP chunk,
reducing the number of small network writes. It verifies TCP_NODELAY with
getsockopt and reports the value in every frame; GET /camera also reports the
actual Wi-Fi power-save mode. Encoding, fixed-profile defaults and motion
watchdogs are unchanged. Transport compatibility tests decode both the previous
two-chunk response and the new single-chunk response with Python's HTTP decoder.
All 38 tests and Ruff passed, and the built firmware was flashed with hash
verification.

The v0.4.3 five-minute 8 FPS/Q75 trial at
`.local/benchmarks/20260926-111129-8fps-q75-single-chunk` collected 2399 valid,
unique-timestamp images: 7.9967 effective FPS, minimum ten-second rate 7.9 FPS,
zero observed missing sequences/retries/stale frames/missed encoder slots,
one device boot ID and zero Wi-Fi association disconnects. Every frame verified
320x240/Q75/8 FPS and TCP_NODELAY=1; final device status verified Wi-Fi power
save mode 0 (none). Maximum capture interval was 250.24 ms, maximum delivery
interval 268.48 ms, p95 delivery interval 205.75 ms. Encode p95 was 76.39 ms and
send p95 94.74 ms. This passed the explicit collection test. The stricter timing
check did not pass: delivery interval p95 deviation was 90.64 ms, so the result
does not establish exact 125 ms arrival intervals.

The final scene contains a hand/device and laptop, and JPEGs averaged 8.18 KB
(0.524 Mbps received payload), versus 14.62 KB in the baseline. Signal ranged
-62 to -57 dBm, median -60. The pass is qualified to these conditions; smaller
images and changed position prevent attributing the improvement solely to the
single-chunk change. All four trials used camera-only collection, without LEGO
or head requests. The fixed default remains 8 FPS/Q75; no automatic adaptation
or recording classification was introduced. Consolidated evidence is saved in
`.local/benchmarks/comparison.json`. Next validation is the same test with a
representative toy-road scene, then head control and driving, before claiming
complete robot data-collection stability.

## Direct Wi-Fi with Ethernet internet (2026-09-26)

The operator connected a USB Ethernet adapter and requested Ethernet internet
plus direct Stack Chan Wi-Fi. The adapter is en7, service USB 10/100/1000 LAN,
with an active 1 Gbps link and DHCP address 10.0.0.128. An HTTPS request bound
to en7 returned 200. Moving that service ahead of Wi-Fi changed the default
internet route to en7; all other services retained their relative order. The
previous order is saved privately under
`.local/network-order-before-direct-wifi.json`.

Firmware v0.4.4 adds USB-requested, password-protected AP-only mode at
192.168.4.1, channel 6, one allowed client. It does not route internet traffic.
The AP flag is consumed before startup: power-cycle or reset returns to saved
home credentials. A nonzero lease automatically returns to station mode;
explicit lease 0 supports staying connected when Ethernet preserves internet.
No capture, quality, motor, head-bound or watchdog behavior changes. Network mode
is recorded in each frame; AP frames omit station RSSI rather than reporting a
misleading signal value. The viewer identifies Direct Wi-Fi or Router Wi-Fi.

The macOS helper uses password stdin for networksetup and private local files;
credentials never appear in command arguments or benchmark reports. It verifies
the separate internet route and HTTPS before/after joining the AP, arms a
detached recovery process before the first network change, restores the private
camera configuration on failure and can keep direct Wi-Fi after a completed
trial. Recovery tests cover lost USB, failed Mac association, idempotence,
password handling and rejected internet routes. Read-only preflight uses HTTP,
with a regression test rejecting USB/network mutations.

A startup probe exposed a separate diagnostic issue: opening the USB status
port restarted the board (HTTP boot ID changed from 268404918 to 1418448692).
Repeated short USB readiness polls caused repeated startup rather than a useful
baseline. A continuous open showed normal encoding after startup. Measurements
now use HTTP readiness and no USB polls during capture; USB is used only for the
explicit mode change or recovery. This does not explain pauses in the earlier
benchmarks, which observed a single boot ID throughout each trial. Firmware build
and flash completed, hash verified, and targeted host tests and Ruff passed.

The controlled comparison collects a five-minute 8 FPS/Q75 home-router baseline
with Mac internet/camera LAN traffic through Ethernet, then a five-minute direct
AP trial with Mac Wi-Fi for camera and Ethernet for internet. The operator was
asked to keep scene/position fixed. Results are appended after both trials.

After AP association, route inspection verified camera traffic to 192.168.4.1
uses en0, while the default internet route remains en7. Authenticated camera
status reports network_mode=ap and one associated client. macOS networksetup's
SSID query returned unassociated despite the valid route and live camera;
interface routing and live device/frame telemetry are the connection evidence.

The AP's raw esp_wifi_get_ps value is 1; this should not be presented as measured
AP modem sleep. The installed Arduino setSleep implementation only changes its
cached policy when STA is not started. Espressif documents modem sleep as a
station-only feature:
https://docs.espressif.com/projects/esp-idf/en/latest/esp32s3/api-guides/wifi-driver/wifi-performance-and-power-save.html
No AP sleep optimization was introduced during the comparison.

Both five-minute trials completed on v0.4.4 at 320x240/8 FPS/Q75 with 2400
decoded images, unique capture timestamps, one boot ID each, zero observed
missing sequences/retries/stale frames/missed encoder slots and a verified fixed
profile. The home-router/Ethernet baseline had minimum ten-second rate 7.9 FPS,
delivery p95 148.63 ms, max delivery gap 291.72 ms, encode p95 76.66 ms and send
p95 29.86 ms. It passed collection criteria but failed the strict timing check
on that maximum delivery gap. Direct AP had exactly 8 FPS in all 30 ten-second
windows, delivery p95 135.80 ms, max delivery gap 181.79 ms, encode p95 76.21 ms
and send p95 19.18 ms. It passed both collection and timing checks. Maximum
capture gaps were approximately 250 ms in both; real timestamps are retained.

Both first images show the same laptop/table scene; JPEGs averaged 9903 and
9772 bytes, approximately 1.3% different. This is a substantially more comparable
pair than the earlier compression/FPS trials. Both paths passed collection,
so this does not identify the earlier intermittent-pause root cause or establish
stability while driving or moving the head.

Three complete 4 MiB direct-AP transfers, with the encoder still running, took
6.231, 6.193 and 6.286 seconds: 5.385, 5.418 and 5.338 Mbps, no errors. The
current image payload is 0.625 Mbps, giving at least 8.54x bulk throughput
headroom for this scene (not a bound on latency or future scene size). Default
internet route remains en7; a normal IPv4 HTTPS request returned 200 with local
address 10.0.0.128 after the AP test. The recovery watchdog was cancelled after
completion, direct Wi-Fi remains connected, and the video-only viewer was
reopened. All 44 host tests and Ruff passed. Consolidated results are saved in
`.local/benchmarks/direct-wifi-comparison.json`. Operator recording labels are
unchanged; AP credentials remain private.

## Increased FPS and JPEG quality (2026-09-26)

The operator requested 10 FPS and higher JPEG quality. The first explicit trial
used 10 FPS/Q85, keeping 320x240 and direct AP with Ethernet internet. In five
minutes it collected 2997 decoded images (9.99 effective FPS), minimum
ten-second rate 9.8 FPS, zero retries/stale frames and no newly missed encoder
slots. One encoded sequence was missing at about 87 seconds: the prior send
took 247.53 ms, while the two adjacent encodes were 82.75 and 78.81 ms. Maximum
delivery gap was 313.46 ms. This fails the zero-missing-sequence collection
criterion. Encode p95 was 79.58 ms of the 100 ms target period; send p95 23.09 ms.
Image payload averaged 0.957 Mbps, so the earlier measured 5.34 Mbps bulk
capacity still provides bandwidth headroom; the isolated stall is not proof of
sustained bandwidth saturation. This trial observed one unchanged device boot ID.
The raw encoder missed-slot counter started at 2 and remained at 2 throughout;
the report counts the zero increase during this trial.

Recording inspection now uses the profile saved in episode metadata, and the
first actual frame sets its gap threshold to two target periods. This prevents
10 FPS recordings from being incorrectly assessed against the old 8 FPS/Q75
default. A regression test writes/decodes real JPEGs in a 10 FPS/Q85 episode and
verifies its timing report while preserving the operator's success label. The
focused camera tests and Ruff passed. No automatic labels were introduced.

The operator subsequently accepted 1–2 missing images and explicitly selected
10 FPS/Q85. The completed Q85 trial is within that stated tolerance; its
historical zero-loss benchmark result is retained unchanged. The session now
uses fixed 320x240/10 FPS/Q85 on direct Wi-Fi, with Ethernet internet, and the
camera-only preview was reopened. The settings remain runtime-only; a reset
restores saved home Wi-Fi and the firmware default 8 FPS/Q75.

The follow-up Q80 diagnostic finished after the runtime profile was switched to
the selected Q85 setting. It contains 2468 Q80 images and 533 Q85 images, so its
aggregate is not a valid fixed-profile comparison. An operator note is saved
beside that diagnostic report. No training recordings or their labels changed.

## Direct LEGO Bluetooth control investigation (2026-09-26)

The Mac connects directly to LEGO using Bleak; Stack Chan is not a Bluetooth
relay. Real GATT reads identify Pybricks 4.0.1 with communication profile 1.5.0.
Official Pybricks guidance limits idle shutdown to disconnected hubs without a
running program:
https://pybricks.com/learn/getting-started/pybricks-environment/
The bridge's own 400 ms watchdog brakes the motors, without shutdown/disconnect.

An initial zero-power run completed 600 GATT writes, remained connected through
five seconds without application messages, and then answered PONG. Although
targeting 10 Hz, its measured throughput was only 7.90 Hz, GATT acknowledgment
p95 179.97 ms and maximum 299.97 ms. Idle traffic absence does not explain the
previous BUSY errors; their original driving-only trigger is still unknown.

Drive writes now append the existing PING byte to the three-byte power packet,
then require a fresh PONG before another control cycle. This proves the bridge
processed the preceding motor instruction and limits unconsumed commands to one.
No hub upload or firmware change was needed. A stale PONG or GATT acknowledgment
alone cannot complete a command; fragmented fresh replies are supported. Events
carry hub_consumed=true, with send-start and confirmation times preserved.
Legacy commands remain transport acknowledgments only. Physical wheel response
is not measured. Slow replies still disarm and recover at zero power; no motion
is replayed. Confirmed command Hz and reply p95 now appear in the driving HUD.

The production-loop zero-power benchmark confirmed 934 commands in 120 seconds
with camera streaming at 10 FPS/Q85: 7.775 Hz, reply p95 180.31 ms, max 302.01 ms,
three slow-reply recoveries, no BUSY events or link failures. A 30-second trial
with video stopped but Wi-Fi still associated gave 232 commands, 7.715 Hz, p95
181.76 ms, max 299.40 ms, no recoveries/BUSY. With Mac Wi-Fi off and Ethernet
internet maintained, another 30-second trial gave 249 commands, 8.283 Hz, p95
121.23 ms, max 180.27 ms, no recoveries/BUSY. None met the 10 Hz acceptance
criterion. Wi-Fi association appears to contribute to latency in this fixture,
but the tests do not isolate the remaining Bluetooth/firmware/host delay.

The explicit benchmark writes only zero power and keeps its results outside
training recordings. Full comparison is in .local/ble-tests/comparison.json.
All 47 host tests and Ruff passed. After testing, direct AP was restored,
authenticated HTTP verified 10 FPS/Q85 with the same camera boot ID, Ethernet
internet was verified, and the normal driving window reopened disarmed. Actual
driving stability remains unverified; no claim of a resolved original BUSY
cause or reliable 10 Hz control is made.

## Open-loop motor commands and 1 Hz heartbeat (2026-09-26)

At the operator's request, the per-command PONG confirmation was removed.
Motor updates send only the three-byte drive command and do not wait for an
application reply. Approximately once per second, a PING byte shares the same
GATT write; asynchronous PONG notifications refresh a heartbeat timestamp. A
missing heartbeat for 2.5 seconds disarms and closes the BLE link. Startup and
fault recovery still use a bounded explicit PING/PONG check. The independent
400 ms motor watchdog, input/camera expiry, slow-write disarm, and manual rearm
remain in place.

The host has no application control-command queue. Each cycle samples the
latest Controls state, with at most one GATT write in flight; intermediate input
updates are overwritten and delayed motion is never replayed. Pybricks' required
write-with-response operation and its underlying stdin receive storage remain;
this is not a claim of zero buffering throughout Bluetooth or hub firmware.
Official profile specification states write-without-response is unsupported:
https://github.com/pybricks/technical-info/blob/master/pybricks-ble-profile.md
Command events now state transport_ack=true and hub_consumed=false, and heartbeat
replies have their own events. The HUD labels the rate as sent and shows write
ACK p95 and heartbeat age. Historical recordings and test reports were retained.

The 30-second production-loop zero-power trial, with 10 FPS/Q85 camera streaming
over direct Wi-Fi, completed 233 acknowledged writes at 7.734 Hz. All 28
heartbeat requests received replies; there were no BUSY events or disconnects.
ACK p95 was 179.96 ms, maximum 301.03 ms, with three slow-write stop/recovery
events. It failed the strict 10 Hz rate criterion. Removing application replies
therefore did not resolve the transport delay in this fixture. Report:
.local/ble-tests/20260926-121430-open-loop-10hz/report.json.

All 50 host tests and Ruff passed, including drive completion without PONG,
nonblocking heartbeat requests and fragmented replies, replacement of
intermediate joystick commands, and heartbeat-loss disarm/disconnect while
video remains independent. No hub firmware upload was required. Camera HTTP
status still reports direct AP at 10 FPS/Q85 with boot ID 3241788962. The normal
driving window was reopened disarmed after the zero-power test; physical driving
with this change remains unverified.

## Fast joystick polling and per-image action pairing (2026-09-26)

The Stadia controller was reconnected and detected with six axes and seventeen
buttons. SDL input remains on the main/UI thread, now targeting 120 Hz independently
of 30 Hz rendering. Actual polling Hz is measured from host sample timestamps;
it is not the controller's physical Bluetooth report rate. Existing left/right
stick mappings and all drive/head stop behavior are retained.

Controls retains a bounded five-second input history only for recording alignment;
motor control continues reading one latest state, with no command FIFO. Each
camera event selects the latest sample at or before estimated_capture_t, so an
input read after capture cannot leak into that image's action label. A repeated
input retains its original timestamp and age. Absent or expired (>250 ms) input
is represented explicitly by action=null and action_valid=false. No operator
recording label is changed. A separate bounded history of completed BLE writes
provides last_ble_command at or before capture; future writes are excluded.

Schema 5 frame events carry the safety-gated requested action and a joystick
object with raw/requested drive/head axes, timestamp, source/controller, connection,
focus/stop/armed state, age, and freshness. Actual motor transmission remains a
separate stream; a slower BLE rate is not hidden by duplicating transport events.
Clock alignment is still estimated and does not establish hardware synchronization
or measured wheel state. Existing recordings are retained. The HUD and metadata
count per-image actions separately from physical BLE writes.

The explicit motion-disabled input test collected 98 real JPEGs with 98 valid
Stadia samples and zero images missing an action sample. Measured median host
polling was 115.225 Hz; maximum sample age at estimated capture was 8.554 ms.
Every selected sample preceded estimated capture. Requested throttle ranged
from -0.834 to 1.0 and steering from -0.834 to 0.790, verifying live changing
input in both directions. Safety-gated actions were zero because this test
disables motor and head workers. No BLE or head commands were sent.

Camera delivery was 9.935 FPS with fixed 10 FPS/Q85 and no missing sequences,
reconnects, stale frames, or newly missed encoder slots. The recording is isolated
at .local/joystick-tests/20260926-122008-46eb012a. Its inspector decoded all JPEGs.
All 55 host tests and Ruff passed, including causal sample selection, held input
across images, explicit stale/missing input, disarmed intent versus effective
action, completed BLE write selection, and persistent image/action associations
without changing the operator's success label. Normal driving reopened disarmed.

## Split-stick driving and fixed camera (2026-09-26)

Left vertical controls throttle; right horizontal controls steering. Left horizontal
and right vertical are ignored. Camera positioning runs only at startup: renew the
absolute zero target until servo feedback is within 2° of 0/0, then hold and close
the head connection. Camera streaming and latest-state BLE sending remain independent.
New episode metadata records this mapping and fixed camera mode.

## Slow ACKs are diagnostic (2026-09-26)

Removed the 300 ms ACK disarm and extra zero-power recovery write. An in-flight
write remains the only command; the next cycle reads current joystick state.
Piggyback heartbeat requests target 250 ms intervals; a one-second missing-PONG
deadline is checked during pending writes. The hub command watchdog is changed
from 400 ms to one second to match. Operator/input/video stop behavior remains
active. Metadata stores this policy.

## Abandoned-session recovery (2026-09-26)

The bridge exits after five seconds without a valid complete drive command or
PING. Motor braking remains at one second without a drive command. Nonblocking
byte parsing and a 250 ms partial-packet timeout prevent incomplete input from
freezing either timer. Mac zero/EXIT cleanup is limited to 750 ms and BLE
disconnection to two seconds, with disconnect attempted even after a stalled
stop write. Reconnecting starts the saved bridge disarmed.

## Always-available controller input (2026-09-26)

Removed the arm/disarm state and E action. Gamepad input remains active with
SDL background joystick events enabled; window focus gates only keyboard input.
Space and A send zero only while held, and recording save/reject does not
change drive state. Connection/video/input freshness gates remain temporary.
LEGO reconnects automatically, then consumes current input after zero-power
READY/PONG startup; no old command queue is replayed. Schema 6 records
drive_available instead of armed; historical datasets remain unchanged.

## Recording pause/resume (2026-09-26)

Space toggles recording pause/resume; motor stop remains momentary gamepad A.
Schema 7 records active intervals, recording_segment IDs, pause/resume events,
and active duration. Image eligibility uses estimated capture time so late
images from paused intervals cannot leak into resumed data. Timing checks ignore
intentional segment boundaries while detecting actual losses within segments.
Playback, BLE sending, and joystick polling continue during a pause.


## LCD action layer (2026-09-26)

Firmware 0.5.0 adds six LCD emotions, natural blinking/screen gaze, and a silent
mouth animation. `./app faces` serves a local test panel; it does not load a
policy, initialize a controller, connect to LEGO, or write expert recordings.
`FaceClient` sends authenticated `/face` actions on HTTP 81, independently of the
camera stream on HTTP 80 and the Mac's direct BLE wheel connection. Later race
and ER2 mode controllers can reuse this action boundary. Speech and a complete
mode switcher are not implemented in this increment.

The LCD worker uses SPI at lower priority than capture. Its animation target is
8 FPS; after its initial full-screen redraw it pushes just the face and the
sleepy-decoration regions, preventing leftover decorations and avoiding a full
76,800-pixel transfer each tick. Canvas snapshots use PSRAM, copy under a mutex,
and release it before network transmission. Previews refresh only on selection
or manual request. Accepted-action and rendered-action revision counters let the
panel wait for the selected face before taking a snapshot. All I2C/audio/touch
operations remain excluded while the camera owns the internal bus; the physical
head starts at 0°,0° and the face layer never moves it.

Validation: 107 host tests passed. Firmware compiled and esptool verified the
written binary. All six board-rendered canvases were inspected; invalid fields,
invalid types and unauthorized actions were rejected without changing the
expression. The actual LCD is driven from this canvas; the preview evidence is
a buffer snapshot, not a photograph of the physical display.

A first full-screen-redraw trial averaged 9.90 camera FPS, had no missing encoded
sequences/reconnects, but a 250 ms sensor timestamp gap failed the stricter
capture-interval check. After partial refresh, a 60-second direct-AP test with
all six emotions cycling and silent talking active collected 599 valid 320×240
Q85 images (9.983 FPS), with no missing sequences, reconnects, stale frames or
source missed slots. Longest sensor interval was 200 ms and longest delivery gap
154 ms; the existing collection and timing criteria passed. The LCD averaged
5.32 redraws/second under this combined workload (8 FPS is its cap, not a measured
guarantee). This is a short
concurrent camera/LCD check, not a driving or speech test. Internet remained on
Ethernet en7. Private evidence is in `.local/face-tests/`, including hardware
checks, six-face contact sheet, final camera report and firmware hashes. The
previous working camera firmware remains in
`.local/firmware-backups/0.4.4-before-faces/`.

## Audio-driven speech action (2026-09-26)

Firmware 0.6.0 initializes the speaker amplifier before handing I²C to the camera.
Subsequent speech uses the initialized I2S driver on independent audio pins. No
M5 update, microphone, touch or amplifier reinitialization runs during capture.
Authenticated `POST /speech` accepts one bounded 20-second 24 kHz mono S16LE clip;
busy requests return 409 instead of queuing. The worker owns PCM memory until the
driver finishes, including a bounded timeout path that retains a buffer if the
driver still owns it. `GET /speech` reports phase, position, mouth ratio and
actual voiced/silent LCD redraw counts.

The mouth follows a 25 ms RMS envelope computed from the played PCM. A noise gate
closes it in silence, with fast attack and a short release. A local scheduled PCM
clock includes approximately 21 ms of DMA delay; the public speaker API exposes no
DAC playhead, so this does not claim measured sample-perfect synchronization.
The renderer targets 20 Hz mouth ticks below capture priority, limits expensive
gaze redraws to twice per second during speech (plus blink/expression transitions),
and returns to 8 Hz idle animation. These are caps rather than guaranteed rates.

The local face panel adds text and Speak using macOS Samantha plus ffmpeg. It
neither contacts a cloud TTS service nor connects to LEGO. Future ER2 audio can
use `FaceClient.speak_pcm`; conversation, microphone capture and full app modes
remain future work. The camera keeps 320×240/10 FPS/Q85 and the head stays at 0°,0°.
Earlier dataset, motor control and policy behavior are unchanged.

Validation: 112 host tests passed and Ruff was clean. Firmware compiled and
esptool verified the installed binary. Real PCM clips completed with both voiced
and silent LCD frames, zero mouth on completion, and busy uploads rejected.
The browser Speak button completed a local synthesis/upload/playback round trip.
Physical audibility and perceived lip timing need operator confirmation; API
state and canvas redraws alone cannot establish those observations.

The first concurrent trial had a 250 ms sensor gap and slower mouth redraws.
After reducing full-face refresh work, the final 30-second direct-AP trial
collected 297 valid Q85 images (9.9 FPS) with zero encoded missing frames,
reconnects, stale frames or source missed slots. Maximum capture interval was
200 ms and delivery gap 182 ms; collection criteria passed. Three clips rendered
71, 38 and 73 mouth frames over 5.802, 3.200 and 5.802 seconds, respectively
(11.9–12.6 FPS), including voiced and silent frames. Evidence, source/binary
hashes and flash verification are in `.local/speech-tests/`; the prior 0.5.0
firmware backup is `.local/firmware-backups/0.5.0-before-audio/`.

## Speaking mouth spectrum (2026-09-26)

Firmware 0.6.1 replaces the opening/closing speech mouth with five rounded bars
centered in the mouth position. Eyes and emotion selection remain the same.
During pauses the bars shrink to dots; completion restores the expression's
normal mouth. No extra LCD region or right-edge widget is drawn.

The PCM preparation pass also computes five broad energy envelopes using an
overlapping low-pass difference filter bank (200/500/1200/3000 Hz boundaries).
All bands share a peak normalization reference to retain relative energy, with
per-band noise gates and smoothed attack/release. This is a lightweight audio
visualization, not calibrated FFT analysis. It uses the existing scheduled PCM
clock, PSRAM buffers, small mouth redraw region and camera priority.
`GET /speech` adds `audio_bands`, `displayed_audio_bands`, `audio_level` and
`audio_visual: mouth_spectrum`. Legacy mouth-level fields remain compatibility
aliases; they no longer imply lip shapes. The face panel uses spectrum wording.
The 0.6.0 binary is backed up under
`.local/firmware-backups/0.6.0-before-spectrum/`.

Validation: firmware compiled and esptool verified its flash. A board test with
100 Hz and 4 kHz tones verified independent low/high displayed band levels and
zero levels on completion. Active/idle board canvas snapshots were inspected.
A separate 20-second camera run during two speech clips collected 198 valid
320×240/Q85 images (9.9 FPS), with no missing sequences, reconnects, stale frames
or source missed slots; maximum sensor interval was 199 ms and collection criteria
passed. Audio glyph redraws measured 7.6 and 11.0 FPS in these clips, below the
20 FPS cap. Private evidence and firmware hashes are `.local/spectrum-tests/`.

## Larger persistent audio mouth (2026-09-26)

Firmware 0.6.2 doubles the spectrum glyph width to 64 pixels (8-pixel bars,
14-pixel spacing) and doubles peak bar heights to 20/28/40/56/72 pixels.
Resting bars remain visible at 8/10/12/16/20 pixels; completion no longer restores
an expression mouth. The center moves down to y=180 so tall bars clear the eyes.
The partial update region expands to 88×78, and full-face transfers include its
bottom edge to prevent clipping or stale pixels. Emotion eyes, happy cheeks and
sleepy decoration remain. The previous 0.6.1 firmware is backed up under
`.local/firmware-backups/0.6.1-before-large-bars/`.

Validation: compiled and flashed with esptool verification. Static board canvases
before/after playback were identical, demonstrating persistent resting bars;
active and happy canvases were inspected. Inspection caught an M5GFX color-type
mismatch in the new clear rectangle; an explicit uint32_t RGB value fixes it.
After the corrected flash, active/idle canvases were inspected again, the clear
region matched the face background, and idle canvases before/after speech remained
identical.
A 20-second concurrent camera check collected 196 images (9.8 FPS), with no
missing encoded frames, reconnects or stale frames. One 250 ms sensor interval
exceeded the existing strict two-period timing limit; this short check does not
establish constant camera cadence. Evidence is `.local/large-bars-tests/`.

## Equal spectrum height range (2026-09-26)

Firmware 0.6.3 removes the ascending resting heights and per-position peak
limits. Every bar now rests at 12 pixels and maps its measured energy to the
same 12–72 pixel height range. The broad filter bank, shared normalization,
64-pixel glyph width, colors, persistent idle state and drawing region remain.
The previous 0.6.2 binary is backed up under
`.local/firmware-backups/0.6.2-before-equal-bars/`.

Validation: compiled and flashed with esptool verification. Actual rendered bar
heights were 12/12/12/12/12 at idle, 72/34/21/16/12 during a 100 Hz tone, and
19/23/37/65/72 during a 4 kHz tone. Both clips completed and returned to the equal
idle heights. Board-rendered canvases were inspected; camera runtime profile was
restored to direct AP/10 FPS/Q85 without another timing benchmark for this scale
change. Evidence and firmware hashes are `.local/equal-bars-tests/`.

## Robot voice tryout (2026-09-26)

The local face panel adds Zarvox and Trinoids alongside Samantha in a voice picker,
initially selecting Zarvox. `/speak` accepts an optional allowlisted `voice` value;
omission preserves the previous Samantha behavior. The selected name is passed to
macOS say as a subprocess argument, then audio follows the existing 24 kHz mono PCM
path. No firmware, LEGO or recording changes are involved. Focused face tests
passed (16 tests) and Ruff was clean. Both voices synthesized locally; Zarvox
completed through the browser Speak action with 65 voiced LCD redraws. Samples
and device playback reports are under `.local/voice-tests/`.
Trinoids also completed through the browser with 60 voiced redraws; both replies
ended at zero audio levels. An unknown voice was rejected with HTTP 400 before
speech generation.

## Local neural voice and future conversation references (2026-09-26)

Face Lab now defaults to Kokoro-82M v1.0 int8 / `am_puck` at 1.03×, matching
the Stack Chan simulator and Silly TurtleBot. `speech.py` owns verified pinned
model setup, the lazily loaded local engine, English voice inventory and the
24 kHz mono S16LE conversion boundary. The UI groups 28 English neural voices
separately from installed macOS system voices. Existing system names remain
accepted; omitted voice selects Kokoro Puck. Assets stay under ignored
`.local/models/`, and the uv lock pins the runtime and transitive dependencies.
There is no firmware, motor, capture or policy change.

The Silly TurtleBot audio input, separate local TTS, persistent ER2 session,
latest-frame image pump and event feedback were inspected. Details and future
mode boundaries are in `speech-references.md`. We have not implemented microphone
capture, continuous audio input, ER2 connection or mode switching in this slice.

Validation: Ruff clean and 120 host tests passed. Real Puck, Heart and Emma
phrases synthesized to 24 kHz mono PCM in 3.349, 1.668 and 2.259 seconds,
respectively (Puck includes first engine load). Their padded durations were
3.487, 3.572 and 3.615 seconds. Tests cover signed endpoint conversion without
overflow, invalid/nonfinite/duration/rate rejection, neural default selection,
unknown voices and busy refusal before synthesis. These are warm-cache local
results, not a clean-cache first-run reproduction or a camera timing benchmark.
Private samples and synthesis timings are `.local/kokoro-tests/`.
The reopened browser panel's Speak action uploaded Puck as clip 9. The board
reported preparing, playing and complete over 3.486 seconds, with 34 voiced
and 18 silent LCD redraws and zero displayed energy on completion. The browser
returned to “Finished · audio bars resting” with Speak available. This verifies
the neural synthesis/upload/playback/visualization path; perceived voice quality
and physical audibility still require listening by the operator.
