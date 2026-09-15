# LEGO Powered Up Teleop

Drive a two-motor LEGO differential-drive robot from a small Python control pad
over Bluetooth Low Energy.

The controls are hold-to-drive: releasing the mouse, key, or analog stick sends zero power. The
hub also brakes both motors if commands stop for 400 ms, so a closed window,
crashed Python process, or lost Bluetooth link fails stopped.

## Supported hubs

This first version targets hubs that can run the documented Pybricks
computer-communication program:

- City Hub
- Technic Hub
- SPIKE Essential Hub
- SPIKE Prime / MINDSTORMS Inventor Hub

The BOOST Move Hub lacks the `usys`/`uselect` interface used by this bridge. The
newer Technic Move Hub cannot currently install Pybricks firmware. Those two
would need a stock LEGO Wireless Protocol transport instead.

## Five-minute setup

1. Put the robot on a stand so its wheels cannot touch the floor.

2. In Chrome or Edge, open [Pybricks Code](https://code.pybricks.com), then use
   **Tools → Install Pybricks Firmware**. Installing Pybricks is reversible;
   the same Tools menu can restore the official LEGO firmware.

3. Open [`hub/main.py`](hub/main.py) in Pybricks Code. Its defaults are a left
   motor on port A and a right motor on port B, mounted as mirrored wheels:

   ```python
   LEFT_PORT = Port.A
   RIGHT_PORT = Port.B
   LEFT_POSITIVE = Direction.CLOCKWISE
   RIGHT_POSITIVE = Direction.COUNTERCLOCKWISE
   ```

   Change those four lines if needed. The bridge automatically accepts encoded
   robotics motors and simpler train-style DC motors. Save/run the program once
   so it is stored on the hub, stop it, and disconnect Pybricks Code.

4. Build and check the desktop app:

   ```bash
   ./app build
   ./app check
   ```

5. Turn the hub on, then run:

   ```bash
   ./app doctor
   ./app smoke       # stays at zero motor power
   ./app run
   ```

The desktop app connects and starts the saved bridge automatically.

### Optional Stadia Bluetooth controller

Pair the Stadia controller with the Mac in **System Settings → Bluetooth**.
Unlike the LEGO hub, the controller is an operating-system HID device, so it
should be paired normally. The app can use the gamepad and its separate BLE
connection to the hub at the same time.

Check the controller before connecting the robot:

```bash
./app gamepad
```

Move the left stick vertically and verify that up shows positive throttle. Move
the right stick horizontally and verify that right shows positive steering. A
should show `stop=YES`. Press Ctrl-C when finished. The app detects a controller
connected before or after the window opens.

## Controls

| Action | Stadia controller | Keyboard | Window |
|---|---|---|---|
| Forward / reverse | Left stick up/down or D-pad | Up/down or W/S | Hold FWD/BACK |
| Turn left / right | Right stick left/right or D-pad | Left/right or A/D | Hold LEFT/RIGHT |
| Stop immediately | A | Space | STOP |
| Change power cap | — | `-` / `+` | − / + |
| Retry Bluetooth | — | R | Retry connection |
| Quit safely | — | Q or Escape | Close window |

Power starts at 35% and is limited to 10–60% in the UI. Simultaneous forward
and turn keys produce an arc; wheel powers are scaled together so the curve is
preserved.

Both stick axes are proportional: small movement gives low wheel power and full
movement reaches the selected power cap. A 10% center deadzone prevents stick
noise from moving the robot; tune it with `--gamepad-deadzone 0.15` if needed.

If more than one hub is nearby, name the one to use:

```bash
./app hubs
./app run --hub-name "Robot Red"
```

## First movement check

Keep the wheels lifted and briefly hold Forward. Both wheels should propel the
robot forward when placed down. If one wheel is reversed, change only that
motor's `Direction` in `hub/main.py`, save it to the hub again, and repeat the
stopped smoke before driving on the floor.

This robot's wheels-up calibration inverts the host throttle axis while leaving
steering unchanged. That calibration applies equally to the window, keyboard,
and Stadia controller.

For the first floor run, use a clear area, stay within reach, and keep the 35%
default. The center button on the hub also stops its running program.

## Safety behavior

The stop path is deliberately redundant:

1. Releasing a UI control sets the desired wheel powers to zero.
2. The BLE worker re-sends the current command at 10 Hz.
3. Closing the app sends zero and asks the bridge to exit.
4. The hub brakes locally after 400 ms without a drive packet.
5. The hub's physical center button stops the Pybricks program.

The hardware smoke starts the saved program, proves both configured motor
objects initialized by waiting for `READY`, sends only zero motor power, and
checks a `PING`/`PONG` round trip.

## Troubleshooting

**No advertising Pybricks hub found**

- Turn the hub on immediately before scanning.
- Disconnect Pybricks Code and the official LEGO app; only one BLE client can
  own the hub.
- Do not pair the hub in macOS Bluetooth Settings. Applications connect to it
  directly.
- On macOS, allow Bluetooth access when Python or Terminal asks.

**The Stadia controller is not found**

- Pair it in macOS Bluetooth Settings, then run `./app gamepad` again.
- If it was never converted to Bluetooth mode, it must already have received
  Google's one-time Bluetooth firmware update; ordinary Wi-Fi-mode Stadia
  controllers do not expose Bluetooth gamepad input.
- The controller may appear under a slightly different name; any gamepad shown
  by `./app gamepad` is accepted.

**Connected, but the bridge did not report READY**

- Make sure this repository's `hub/main.py` is the program saved on the hub.
- Check that both configured ports contain motors.
- An `ENODEV` on `left_motor` means `LEFT_PORT` does not contain a recognized
  motor; the equivalent error on `right_motor` means the same for `RIGHT_PORT`.
- Confirm the hub is not a BOOST Move Hub or Technic Move Hub.

**The app crashed or Bluetooth disappeared while moving**

The hub watchdog brakes the motors. Its program may still be running; press the
hub center button once to stop it, then power/advertise the hub and retry.

## Development

```bash
make check        # hardware-free lint and tests
make smoke        # tests, then stopped real-hub PING/PONG
```

See [`docs/architecture-brief.md`](docs/architecture-brief.md) for the module
boundary, safety decisions, and authorized fallback for unsupported hubs.

Pybricks and LEGO are independent projects. LEGO® is a trademark of the LEGO
Group, which does not sponsor or endorse this application.
