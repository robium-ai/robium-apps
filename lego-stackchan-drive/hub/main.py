"""Pybricks bridge for a two-motor LEGO Powered Up differential drive.

Save this program to the hub with https://code.pybricks.com. The desktop app
starts it over BLE and streams three-byte drive packets. The watchdog brakes
both motors if those packets stop, independently of the desktop process.
"""

from pybricks.parameters import Direction, Port
from pybricks.pupdevices import DCMotor, Motor
from pybricks.tools import StopWatch, wait

# Edit these four lines to match the physical build. Positive power must make
# each wheel move the robot forward. Mirrored wheels normally need opposite
# positive directions, as in this D/B layout.
LEFT_PORT = Port.D
RIGHT_PORT = Port.B
LEFT_POSITIVE = Direction.CLOCKWISE
RIGHT_POSITIVE = Direction.COUNTERCLOCKWISE

WATCHDOG_MS = 1000
SESSION_IDLE_MS = 5000
PACKET_TIMEOUT_MS = 250
POWER_BIAS = 100

def attach_motor(port, positive_direction):
    """Accept encoded robotics motors and simple train-style DC motors."""
    try:
        return Motor(port, positive_direction)
    except OSError:
        return DCMotor(port, positive_direction)


left_motor = attach_motor(LEFT_PORT, LEFT_POSITIVE)
right_motor = attach_motor(RIGHT_PORT, RIGHT_POSITIVE)

# Standard streams are the Pybricks Bluetooth transport while a host is
# connected. poll() lets the watchdog keep running when no bytes arrive.
from usys import stdin, stdout
from uselect import poll

incoming = poll()
incoming.register(stdin)
watchdog = StopWatch()
session_idle = StopWatch()
packet_watch = StopWatch()
payload = None
moving = False


def brake():
    global moving
    left_motor.brake()
    right_motor.brake()
    moving = False


brake()
stdout.buffer.write(b"READY\n")

try:
    while True:
        # Read only bytes poll() says are available. A truncated drive packet
        # must not block the motor watchdog or the abandoned-session timeout.
        if payload is not None and packet_watch.time() >= PACKET_TIMEOUT_MS:
            payload = None
        if incoming.poll(10):
            command = stdin.buffer.read(1)
            if not command:
                break
            if payload is not None:
                payload.extend(command)
                if len(payload) == 2:
                    left_power = payload[0] - POWER_BIAS
                    right_power = payload[1] - POWER_BIAS
                    payload = None
                    if not (-100 <= left_power <= 100 and -100 <= right_power <= 100):
                        brake()
                        continue
                    if left_power == 0 and right_power == 0:
                        brake()
                    else:
                        left_motor.dc(left_power)
                        right_motor.dc(right_power)
                        moving = True
                    watchdog.reset()
                    session_idle.reset()
            elif command == b"D":
                payload = bytearray()
                packet_watch.reset()
            elif command == b"P":
                session_idle.reset()
                stdout.buffer.write(b"PONG\n")
            elif command == b"X":
                break

        if moving and watchdog.time() >= WATCHDOG_MS:
            brake()
        if session_idle.time() >= SESSION_IDLE_MS:
            # End the program, leaving the hub powered on for reconnection.
            break
        wait(1)
finally:
    brake()
