"""Configure camera Wi-Fi over USB from private local files."""
import argparse
import json
import os
from pathlib import Path
import secrets
import time

import serial

parser = argparse.ArgumentParser()
parser.add_argument('--port', default='/dev/cu.usbmodem101')
parser.add_argument('--status', action='store_true')
args = parser.parse_args()
root = Path(__file__).parent / '.local'


def request(command, timeout=5, **fields):
    connection = serial.Serial()
    connection.port = args.port
    connection.baudrate = 921600
    connection.timeout = 0.2
    connection.dtr = False
    connection.rts = False
    connection.open()
    try:
        connection.reset_input_buffer()
        connection.write(json.dumps({'id': 99, 'command': command, **fields}).encode() + b'\n')
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            line = connection.readline()
            if line.startswith(b'@stackchan '):
                data = json.loads(line[11:])
                if data.get('id') == 99:
                    return data
        raise RuntimeError('Device did not answer')
    finally:
        connection.close()


if args.status:
    print(json.dumps(request('status'), indent=2))
else:
    wifi = json.loads((root / 'wifi.json').read_text())
    key = secrets.token_urlsafe(32)
    result = request('wifi_config', **wifi, key=key)
    if result['status'] != 'saved':
        raise RuntimeError('Wi-Fi settings rejected')
    # Save key immediately so a timeout does not lose the credentials needed for recovery.
    config = {'url': 'http://stackchan-drive.local/stream', 'key': key}
    with os.fdopen(os.open(root / 'camera.json', os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600), 'w') as out:
        json.dump(config, out)
    time.sleep(3)
    end = time.monotonic() + 35
    while time.monotonic() < end:
        try:
            result = request('status')
            if result.get('connected') and result.get('camera_ready'):
                config['url'] = 'http://' + result['ip'] + '/stream'
                (root / 'camera.json').write_text(json.dumps(config))
                print('Camera connected at ' + result['ip'] + '; stream key stored privately.')
                break
        except (RuntimeError, serial.SerialException):
            pass
        time.sleep(1)
    else:
        raise RuntimeError('Wi-Fi connection not confirmed; check 2.4 GHz network and password')
