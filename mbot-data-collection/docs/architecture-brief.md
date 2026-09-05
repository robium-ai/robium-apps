# Architecture brief - mbot-data-collection

## What this is

A real-hardware teleoperation and data-collection app for the Makeblock mBot.
It exists to produce training data: episodes pairing a webcam view with the
human action taken in response to it, in the LeRobot dataset format, for
fine-tuning a vision-language-action policy.

It is the real-robot counterpart to `smolvla-mbot-push`, which does the same
thing in MuJoCo. The two deliberately share an action space and a feature
layout.

## The decisions that shaped it

### Custom firmware, not the Makeblock protocol

The mBot ships with factory firmware speaking Makeblock's binary protocol, and
`mBlock` can flash sketches built on the Makeblock Arduino library. We flash our
own minimal sketch instead.

The reason is latency and honesty about the control loop. Data collection needs
a known, fixed relationship between "the frame I saw" and "the command I sent";
a protocol designed for block-programming has framing, retries, and sensor
polling we neither need nor control. A 40-line sketch with one command per line
gives a round trip under a millisecond and a control tick we can reason about.

The cost is that the board no longer runs stock firmware. That is reversible -
mBlock will reflash it - and the pin assignments are read out of Makeblock's own
library (`MePort.h`, `MeMCore.h`) rather than guessed, so the sketch drives
exactly the pins the stock firmware drives.

### The board is dumb on purpose

The sketch owns two things only: writing the motor pins, and stopping the wheels
when the host goes quiet. Mixing, ramping, speed limits, and calibration all
live in Python.

This is what makes the robot iterable. Every one of those is a parameter someone
will want to change while a robot is on the desk in front of them, and a
reflash-per-tweak loop is where hardware projects go to die.

### The watchdog is not optional

The board stops the motors if it hears nothing for 400 ms, and the host sends a
command every control tick even when that command is zero.

Without this, a crashed host, an unplugged cable, or a breakpoint in a debugger
leaves a robot driving into a wall at whatever it was last told. This is the one
piece of policy that cannot live on the laptop, because the laptop is exactly
what might fail.

### Uploading with arduino-cli, after a wrong turn worth recording

`./app flash` compiles and uploads with `arduino-cli`, which is the boring
answer. It is written down because this file briefly argued for something else.

Uploads failed with `not in sync: resp=0x00`. Measurement showed the bootloader
answering exactly one command and then going silent, so the conclusion was that
optiboot's window was too narrow for avrdude's retry spacing, and a hand-written
STK500v1 client was built to catch it. Two further measurements muddied this: a
silent wait of 250 ms produced eight clean commands in a row, which looked like
proof that polling had been overrunning the UART FIFO; and toggling DTR or RTS
changed nothing, which looked like a dead auto-reset circuit.

All of it was downstream of one physical fact. The mBot's Bluetooth module
shares the D0/D1 upload UART, so two drivers were fighting over the mCore's RX
pin. With the module unplugged, stock avrdude uploaded first time and has every
time since. The custom uploader was deleted.

Three lessons, in descending order of how much they cost:

- On a shared bus, exhaust the physical explanation before the protocol one. The
  timing evidence was real and reproducible and still pointed at the wrong
  layer, because every symptom of contention is also a symptom of bad timing.
- Absence of unexpected bytes does not mean absence of contention. An idle UART
  module transmits nothing while still driving the line, and that reasoning was
  used here to wrongly rule the module out.
- A workaround that makes a flaky path slightly less flaky is evidence you have
  not found the cause. The tight-loop client raised the success rate enough to
  feel like progress, which is exactly what delayed the real diagnosis.

The ICSP path below survives from that detour, and earns its place: some mBot
boards have the module soldered on, and those genuinely cannot use the serial
path at all.

### One protocol, two transports

USB and Bluetooth reach the same hardware UART, so the firmware needs no notion
of which is in use. That was the point of keeping the protocol short and ASCII,
and it paid off exactly as intended: the wireless path needed no firmware change
at all.

The host side is not symmetric, though, and the asymmetry is worth recording.
Makeblock's module is BLE, and macOS exposes a `/dev/cu.*` serial port only for
classic Bluetooth. There is no port to open, so the Bluetooth transport is a
GATT client rather than a second serial device, talking to the module's
transparent notify/write characteristic pair.

### Motor commands are streamed, not confirmed

Every command in this protocol has a reply, and the control loop reads none of
them for motor commands.

That is a measurement, not a shortcut. A confirmed round trip over BLE is ~60 ms
against a 50 ms control period, so confirming would drag the loop below its own
rate; streaming measures ~0.1 ms. It is safe because of two decisions that were
already made for other reasons: the loop re-sends a command every tick, so a
dropped one is corrected 50 ms later rather than persisting, and the board stops
itself when it hears nothing, so silence can never read as "keep going".

The cost is a reply stream containing acknowledgements nobody asked for, which
is why replies are matched on their verb rather than taken as the next line -
draining before writing is not sufficient on BLE, where a notification sent
before the drain can arrive after it.

### Calibration is asked, not assumed

Which motor is the left wheel and which way each is wired are assembly facts
that differ between robots. `./app calibrate` spins one motor at a time and asks
what happened, then writes `config.json`.

Assuming them yields a robot that steers backwards, and worse, a dataset in
which "turn left" means different things in different sessions. That kind of
inconsistency is invisible until a policy trained on it behaves erratically.

### Cameras are chosen by name, through a measured index map

The obvious design is a camera index in the config. It is wrong twice over, and
both failures are silent, which is what makes them worth the extra machinery.

macOS renumbers cameras when a Continuity phone joins or leaves, so a stored
index can start pointing at a different lens between sessions. And OpenCV's
index order is not macOS's device order at all: measured on one machine,
AVFoundation lists [MacBook, I930, iPhone] while OpenCV's indices open [I930,
iPhone, MacBook]. Resolving a name to its position in the first list therefore
opens the phone - which is exactly what happened here, twice, because the first
fix assumed the orders agreed.

Neither API exposes the other's ordering, and asking AVFoundation to enumerate
using OpenCV's device-type order does not reproduce it. So the correspondence is
measured: `./app cameras --identify` opens each index once, requests an
oversized frame, and identifies the device by the maximum resolution it grants.

Two rules fell out of it, and both are enforced in tests:

- **Listing must never open a camera.** Discovering devices by opening each
  index in turn works, but opening a Continuity camera *starts* it - the phone
  wakes and shows its capture UI. Names come from AVFoundation metadata, and the
  only step that opens everything is the explicit, cached identify.
- **A name with no measured index is an error, not a guess.** Falling back to
  the AVFoundation position would silently record the wrong camera, and a
  dataset full of the wrong viewpoint is discovered far too late.

### `observation.state` is the previous action

The mBot has no encoders. The last command is the only proprioception available,
so that is what the state feature holds.

The alternative - deriving a pose from something the robot cannot measure -
would train a policy that cannot be deployed on the robot it was recorded from.

### opencv-python-headless, not opencv-python

`smolvla-mbot-push` dropped OpenCV entirely to avoid a duplicate-SDL2 clash with
pygame. This app cannot: it needs a webcam, and OpenCV is the most reliable way
to get one on macOS with index and resolution control.

So the clash was measured rather than assumed, and the assumption turned out to
be wrong. `opencv-python-headless` still vendors an SDL2 through its bundled
ffmpeg, and importing it beside pygame prints macOS's duplicate Objective-C
class warning in *either* import order. Headless does not remove the warning.

It is still the right dependency, for a different reason: headless OpenCV cannot
open a window at all, so pygame is the only library that ever exercises the
duplicated windowing classes. The warning is noise; the crash it warns about
needs two libraries fighting over a window, and only one of these can make one.
Anyone tempted to "fix" this by installing the GUI build would reintroduce the
real hazard while removing nothing.

## Layout

| Path | Role |
| --- | --- |
| `firmware/mbot_bridge/` | the Arduino sketch that runs on the mCore |
| `src/mbot_data_collection/flash.py` | arduino-cli compile + STK500 upload |
| `src/mbot_data_collection/link.py` | the serial protocol client |
| `src/mbot_data_collection/config.py` | action mixing and chassis calibration |
| `src/mbot_data_collection/ui.py` | pygame window and teleop input |
| `src/mbot_data_collection/camera.py` | threaded webcam capture |
| `src/mbot_data_collection/drive.py` | the control loop, and calibration |
| `src/mbot_data_collection/record.py` | episode recording into LeRobotDataset |

## Known limits

- The USB tether bounds where the robot can go. A wireless link over the mBot's
  Bluetooth module is the obvious next step, and the line protocol was kept
  ASCII and short partly to survive that move.
- No sensors are exposed yet. The mCore's ultrasonic and line-follower ports are
  available and the protocol has room for a telemetry verb per sensor; nothing
  reads them today because nothing needs them.
- Recording assumes one camera. A second view would be a features change, not a
  loop change.
