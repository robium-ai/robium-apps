# mBot Data Collection

Drive a real [Makeblock mBot](https://www.makeblock.com/) from your laptop and
record what it saw and what you did, in the LeRobot dataset format, ready to
fine-tune a vision-language-action policy on.

The robot carries no computer of its own. A small Arduino sketch on its mCore
board turns the USB cable into a motor bus, and every decision above that -
mixing, ramping, calibration, recording - happens in Python on the laptop, where
it can be changed without a reflash.

```bash
./app build          # create the uv environment
./app flash          # put the bridge firmware on the mBot (USB, module unplugged)
./app config --port ble   # optional: talk to it over Bluetooth from now on
./app doctor         # check the link, firmware, camera, gamepad
./app gamepad        # optional: find which stick axes your controller uses
./app calibrate      # learn which motor is which, and which way
./app drive          # drive it
```

## Driving

`./app drive` opens the webcam view and gives you the robot:

| | |
| --- | --- |
| **Throttle** | up / down arrow, or `W` / `S` |
| **Steer** | left / right arrow, or `A` / `D` |
| **Stop now** | space |
| **Quit** | `Q` |

A game controller is used automatically when one is attached, with the left
stick as throttle and the right stick as steer; `--keyboard` ignores it. Held
keys ramp toward full deflection rather than snapping to it, because square-wave
demonstrations are poor material to clone.

What you see and what you press are exactly what a policy will later consume and
produce.

## The game controller

The controller connects to the **laptop**, not to the robot, so how it connects
has nothing to do with how the robot connects. Two independent links:

```
controller --(USB or Bluetooth HID)--> laptop --(USB serial or Bluetooth)--> mBot
```

macOS presents a gamepad the same way over either transport, so no code or
configuration changes between them - `./app drive` picks up whatever is attached.

Because the controller plugs into the laptop, **a wired controller costs the
robot no mobility at all**. Only the laptop-to-mBot link decides how far the
robot can roam.

Stick axes differ between controllers, and the defaults here (throttle on axis
1, steer on axis 2) suit an Xbox-style layout. To find yours:

```bash
./app gamepad     # push the sticks; it shows which axis moves
./app drive --throttle-axis 1 --steer-axis 2
```

A note specific to the **Stadia Controller**: it is USB-only out of the box. Its
wireless was Stadia's own protocol, and Bluetooth HID is unlocked by a one-time
Google firmware update that also permanently disables the Wi-Fi features. Stadia
has shut down, so that tool may no longer be available - plan on USB unless the
update was already applied.

## Choosing the camera

```bash
./app cameras --identify           # once per machine
./app config --camera-name I930    # then pin the one you want
```

Pick by **name**. An index is not a stable identifier here, for two separate
reasons, and the second one is nastier than the first.

macOS renumbers cameras when a phone joins or leaves over Continuity, so an
index that meant one lens yesterday can mean another today.

Worse, **OpenCV's index order and macOS's device order genuinely disagree**.
Measured on one Mac:

| | 0 | 1 | 2 |
| --- | --- | --- | --- |
| AVFoundation lists | MacBook | I930 | iPhone |
| OpenCV indices open | I930 | iPhone | MacBook |

So "the camera named I930 is second in the list, therefore index 1" opens the
phone. Nothing in either API exposes the other's order, and asking AVFoundation
to enumerate in OpenCV's order does not reproduce it - so the correspondence is
measured instead. `./app cameras --identify` opens each index once, asks for its
largest frame, and uses that resolution to tell the devices apart. The result is
saved, and asking for a camera by name without it fails loudly rather than
guessing.

That identify step is the only thing here that opens every camera, which is
what briefly wakes a Continuity camera. Everything else - listing, `./app
doctor`, ordinary recording - reads names from AVFoundation and opens only the
one camera you actually chose.

## Recording

```bash
./app build-record   # adds LeRobot; not needed just to drive
./app record --repo-id <you>/mbot-drive --task "drive to the red cup" --episodes 10
```

Space starts and stops an episode, `r` discards one that went badly, `q` quits.
Each frame stores the camera image, the action you commanded, and the action you
commanded on the previous tick as `observation.state` - the mBot has no encoders,
so the last command is the only proprioception there is.

The feature layout deliberately matches the simulated sibling app
[smolvla-mbot-push](../smolvla-mbot-push/), so demonstrations collected here and
there describe the same robot in the same terms.

## USB or Bluetooth

Both, with the same firmware and the same protocol. Makeblock's Bluetooth module
sits on the same hardware UART (D0/D1) that the USB bridge uses, so it is a pipe
rather than a translator: the board cannot tell which one a command arrived
through, and the sketch has no notion of either.

```bash
./app config --port ble      # remember it, so this is typed once
./app drive                  # from then on, everything uses Bluetooth
```

Or say it per command, and let it default the rest of the time:

```bash
./app drive --port ble             # this run, over Bluetooth
./app drive --port ble:<address>   # a specific robot, when two are around
./app drive --port /dev/cu.usbserial-10   # this run, over USB
./app config --port ''             # go back to auto-detection
```

With nothing configured and nothing on USB, the Bluetooth module is tried
anyway rather than failing next to a robot that is powered on and waiting.

### The module is BLE, and that matters

The mBot's module advertises as `Makeblock_LE...` - Bluetooth **Low Energy**, not
classic Bluetooth. macOS creates a `/dev/cu.*` serial port for classic SPP
devices and **never for BLE ones**, so no amount of pairing produces a port for
pyserial to open. Pairing it in System Settings is not required either.

The wireless path is therefore a real GATT client (`bleak`), talking to the
module's HM-10 style transparent pair - notify on `0xFFE2`, write on `0xFFE3` -
which carries the same ASCII lines a serial port would.

### What Bluetooth costs

Measured on this module, a *confirmed* command round-trips in about 60 ms. The
control loop runs at 20 Hz, a 50 ms period, so waiting for acknowledgements
would push the loop below its own rate.

It does not, because motor commands are streamed rather than confirmed: the loop
sends and moves on, which measures ~0.1 ms. That is safe for the same two
reasons the board is built the way it is - a command is re-sent every tick, so a
lost one is corrected 50 ms later, and the board stops itself if it hears
nothing at all. Commands that configure or interrogate the board still wait,
because those happen once and their answers matter.

Two things remain true regardless:

- **Flashing is USB-only, with the module unplugged.** A Bluetooth module cannot
  reset the AVR, so it cannot start an upload, and while attached it contends
  for the same RX pin the uploader needs. Flash first, then go wireless.
- **Bluetooth still adds jitter**, and during recording that jitter lands in the
  dataset, because a policy learns the timing of what it is shown. Prefer USB
  for episodes that matter until you have measured the jitter and accepted it.

## The game controller

The controller connects to the **laptop**, not to the robot, so how it connects
has nothing to do with how the robot connects. Two independent links:

```
controller --(USB or Bluetooth HID)--> laptop --(USB serial or Bluetooth)--> mBot
```

macOS presents a gamepad the same way over either transport, so no code or
configuration changes between them - `./app drive` picks up whatever is attached.

Because the controller plugs into the laptop, **a wired controller costs the
robot no mobility at all**. Only the laptop-to-mBot link decides how far the
robot can roam.

Stick axes differ between controllers, and the defaults here (throttle on axis
1, steer on axis 2) suit an Xbox-style layout. To find yours:

```bash
./app gamepad     # push the sticks; it shows which axis moves
./app drive --throttle-axis 1 --steer-axis 2
```

A note specific to the **Stadia Controller**: it is USB-only out of the box. Its
wireless was Stadia's own protocol, and Bluetooth HID is unlocked by a one-time
Google firmware update that also permanently disables the Wi-Fi features. Stadia
has shut down, so that tool may no longer be available - plan on USB unless the
update was already applied.

## Recording

```bash
./app build-record   # adds LeRobot; not needed just to drive
./app record --repo-id <you>/mbot-drive --task "drive to the red cup" --episodes 10
```

Space starts and stops an episode, `r` discards one that went badly, `q` quits.
Each frame stores the camera image, the action you commanded, and the action you
commanded on the previous tick as `observation.state` - the mBot has no encoders,
so the last command is the only proprioception there is.

The feature layout deliberately matches the simulated sibling app
[smolvla-mbot-push](../smolvla-mbot-push/), so demonstrations collected here and
there describe the same robot in the same terms.

## USB or Bluetooth

Both, with the same firmware and the same protocol. The mBot's Bluetooth module
sits on the same hardware UART (D0/D1) that the USB bridge uses, so the module
is a pipe rather than a translator: the board cannot tell which one a command
arrived through, and neither path needs its own code.

**Over USB** (the default) the port is found automatically:

```bash
./app drive
```

**Over Bluetooth**, pair the module in System Settings, then point at the port
macOS creates for it:

```bash
./app doctor                              # lists the ports it can see
./app drive --port /dev/cu.Makeblock-XXXX
```

The port has to be given explicitly, because a paired module is indistinguishable
by name from any other Bluetooth device. If the module was configured at a rate
other than 115200, match it with `--baud`: the module and the ATmega talk to each
other over that UART, so the module's rate sets the rate for the whole link no
matter what the sketch requests.

Three things are worth knowing before choosing:

- **Flashing is USB-only, with the module unplugged.** A Bluetooth module cannot
  reset the AVR, so it cannot start an upload, and while it is attached it
  contends for the same RX pin the uploader needs. Flash first, then go wireless.
- **Do not expect both at once.** With the module attached, both it and the USB
  bridge drive the board's RX line. That contention is what breaks flashing, and
  there is no reason to think it is harmless during driving.
- **Bluetooth adds latency and jitter.** For teleoperation that is merely
  annoying; for recording it lands in the dataset, because a policy learns the
  timing of what it is shown. Prefer the USB tether for episodes that matter and
  Bluetooth for exploring, unless you have measured the jitter and accepted it.

## What a policy predicts

The action is two numbers - **forward speed and turn rate** - each normalized to
`[-1, 1]`. That is what gets recorded, and it is what a policy like SmolVLA
learns to predict.

| feature | shape | meaning |
| --- | --- | --- |
| `observation.images.webcam` | H x W x 3 | what the robot saw before acting |
| `observation.state` | 2 | the action commanded on the previous tick |
| `action` | 2 | throttle, steer |

The chassis mapping - steer gain, differential mixing, the duty floor and
ceiling - is applied *after* the action, identically when you drive and when a
policy drives:

```
action (throttle, steer)  ->  steer gain  ->  differential mix  ->  duty
```

Two consequences worth understanding before collecting a lot of data.

**The action is deliberately not in physical units.** This mBot has no encoders,
so there is no honest way to record metres per second; the command is what is
knowable. That keeps the layout identical to the simulated sibling app, so a
policy pretrained there fine-tunes here without renaming anything but the camera
key - but it also means an action only means a particular motion *given a
particular chassis configuration*. That configuration is written to
`chassis.json` beside the episodes, and re-recording into a dataset after
changing it prints a warning rather than silently mixing two meanings.

**Battery voltage is an unmodelled variable.** The same duty moves a freshly
charged robot faster than a flat one, and nothing here measures that. It shows
up as demonstrations that disagree with each other for reasons the policy cannot
see. Collecting a dataset across one battery charge, rather than several, avoids
the worst of it.

## Calibration

Which motor drives the left wheel, and which way each one is wired, are facts
about how your particular mBot was assembled. `./app calibrate` spins one motor
at a time and asks you what happened, then writes `config.json`. Guessing
instead would produce a robot that steers backwards - and worse, a dataset in
which "turn left" means different things on different days.

`--min-pwm` is the duty at which the gearboxes actually start turning (default
60) and `--max-pwm` caps the top speed (default 200). Lower `--max-pwm` if the
robot is too twitchy to drive smoothly; that limit is also what keeps recorded
episodes at a speed a policy can reproduce.

`./app calibrate --floor` measures `min_pwm` instead of guessing it, by spinning
the wheels at bisected speeds and asking when they start turning. It is worth
doing once. `min_pwm` sets how slowly the robot can move at all, and a value set
too high is the usual reason a slow-looking robot still feels twitchy: if the
floor is 60 and the ceiling is 100, the gentlest touch of the stick already
commands most of the range, and every demonstration gets recorded near full
tilt.

`--steer-gain` (default 0.45) decides how much of the stick's steer travel is
used. A differential drive turns by running its wheels in opposite directions,
so full steer is a spin-on-the-spot at full speed - far sharper than is useful
for driving, and far sharper than makes a demonstration worth cloning. Lower it
if turns still feel abrupt:

```bash
./app config --steer-gain 0.3
```

There are two separate dead bands, and they are worth keeping straight:

- `--stick-deadzone` (default 0.12) is how much stick travel counts as centred.
  Sticks rarely rest at exactly zero, and without it the robot creeps while
  nobody is touching it - which also writes a nonzero action into every idle
  frame of a recording. Input past the edge is rescaled from zero rather than
  clipped, so motion starts smoothly instead of jumping.
- `--min-pwm` is the motor dead band: the duty below which the wheels do not
  turn at all. Measure it with `./app calibrate --floor` rather than guessing.

The gain belongs to the chassis, not to the action space: what gets recorded is
still the raw stick position, so datasets stay comparable between robots tuned
differently, and a policy replaying an action passes through the same scaling on
its way to the wheels.

## The firmware

`firmware/mbot_bridge/mbot_bridge.ino` is a deliberately dumb sketch. It owns
the two things the laptop cannot do safely across a USB cable: it writes the
motor pins, and it stops the wheels when the host goes quiet.

Motor pins are taken from Makeblock's own library rather than a wiring diagram,
so the sketch drives exactly what the stock firmware drives - `MePort.h` defines
`M1 = 0x09` and `M2 = 0x0a`, and `MeMCore.h` maps those to `{PWM D6, DIR D7}`
and `{PWM D5, DIR D4}`.

One ASCII command per line, one reply per line:

| Command | Meaning |
| --- | --- |
| `M <left> <right>` | set motor duty, each -255..255 |
| `S` | stop |
| `P` | ping |
| `V` | identify |
| `W <ms>` | watchdog timeout, 0 disables |
| `T` | telemetry: duty, ms since last command, uptime |
| `Z <hz> <ms>` | beep |

The watchdog matters more than it looks. Without it a crashed host, a yanked
cable, or a stopped debugger leaves a robot driving into a wall at whatever it
was last told. The host sends a command every control tick, even a zero one.

## When flashing fails

`./app flash` compiles and uploads with `arduino-cli`. If the upload fails with
`avrdude: not in sync: resp=0x00`, the cause is almost always physical:

1. **Unplug the Bluetooth or 2.4G module.** This is the usual cause, and it was
   the cause here. The module sits on the D0/D1 upload UART, so during an upload
   two drivers share the mCore's RX pin and corrupt the handshake. Removing it
   made stock avrdude work first time. Plug it back in afterwards - it is only
   in the way while flashing.
2. **Switch the mBot's power on.** USB alone can brown out the mCore, and the
   USB-serial chip enumerates on bus power whether or not the board behind it is
   properly fed, so a dead battery pack looks like a working connection.
3. **Try another USB cable.** Charge-only cables are common and silent.

`./app doctor` checks each link in the chain and says which one is broken.

### If the Bluetooth module is soldered on

Some mBot v1.1 boards have the module soldered rather than socketed, and then
the serial path cannot be freed at all. Contention on a wire is not something
the host can retry its way out of, so there is no software fix worth attempting;
skip straight to ICSP.

Program over ICSP instead, which does not use D0/D1 at all:

```bash
./app flash --isp usbasp                     # a USBasp or similar, ~$8
./app flash --isp arduino-as-isp --isp-port /dev/cu.usbmodemXXXX
```

For `arduino-as-isp`, load the stock **ArduinoISP** example onto a spare Arduino
and wire six lines to the mBot's ICSP header: MISO, MOSI, SCK, RESET, 5V, GND.
`--isp-port` is the *programmer's* port, not the mBot's.

This writes the sketch with the bootloader appended and sets the Uno fuses, so
the board keeps a working bootloader and a future USB upload stays possible if
the serial path is ever unblocked.

## Requirements

- macOS or Linux, Python 3.12+, [uv](https://docs.astral.sh/uv/)
- A Makeblock mBot (mCore / ATmega328P) on USB. macOS binds its CH340 bridge
  with the built-in `AppleUSBCHCOM` driver, so nothing needs installing.
- `arduino-cli` with the AVR core, for `./app flash` only:
  `brew install arduino-cli && arduino-cli core install arduino:avr`
- Any webcam, for recording.

## Checking it works

```bash
./app doctor    # link, firmware, camera and controller, against the real robot
```

There is no unit-test suite. The parts most worth checking here - that the
wheels turn the way you expect, that the camera pointed at the robot is the one
being recorded - are facts about hardware, and `./app doctor` plus
`./app calibrate` check them against the actual robot rather than against a
model of it.
