"""Pybricks watchdog bridge for Stack Chan's two-motor LEGO robot.

Save this file to the LEGO hub with https://code.pybricks.com. Stack Chan's
host process starts it over BLE and streams fixed three-byte wheel commands.
"""

from pybricks.parameters import Direction, Port
from pybricks.pupdevices import DCMotor, Motor
from pybricks.tools import StopWatch, wait

LEFT_PORT = Port.A
RIGHT_PORT = Port.B
LEFT_POSITIVE = Direction.CLOCKWISE
RIGHT_POSITIVE = Direction.COUNTERCLOCKWISE

WATCHDOG_MS = 400
POWER_BIAS = 100


def attach_motor(port, positive_direction):
    try:
        return Motor(port, positive_direction)
    except OSError:
        return DCMotor(port, positive_direction)


left_motor = attach_motor(LEFT_PORT, LEFT_POSITIVE)
right_motor = attach_motor(RIGHT_PORT, RIGHT_POSITIVE)

from usys import stdin, stdout
from uselect import poll

incoming = poll()
incoming.register(stdin)
watchdog = StopWatch()
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
        if incoming.poll(10):
            command = stdin.buffer.read(1)
            if command == b"D":
                payload = stdin.buffer.read(2)
                if len(payload) != 2:
                    brake()
                    continue
                left_power = payload[0] - POWER_BIAS
                right_power = payload[1] - POWER_BIAS
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
            elif command == b"P":
                stdout.buffer.write(b"PONG\n")
            elif command == b"X":
                break

        if moving and watchdog.time() >= WATCHDOG_MS:
            brake()
        wait(1)
finally:
    brake()
