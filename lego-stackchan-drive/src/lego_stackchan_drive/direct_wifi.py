"""Explicit macOS direct-Wi-Fi experiment with independent home-network recovery.

Default invocation only checks readiness. --run changes the Mac's Wi-Fi network.
Ethernet can preserve internet; otherwise the direct-link test is offline.
"""

import argparse
import fcntl
import json
import os
import secrets
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

import serial


def write_private(path, value):
    temporary = path.with_suffix('.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'w') as output:
        json.dump(value, output, indent=2)
        output.write('\n')
    os.replace(temporary, path)


def device_request(port, command, timeout=10, **fields):
    connection = serial.Serial()
    connection.port, connection.baudrate = port, 921600
    connection.timeout = .2
    connection.dtr = connection.rts = False
    connection.open()
    try:
        connection.reset_input_buffer()
        connection.write(json.dumps({'id': 191, 'command': command, **fields}).encode() + b'\n')
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = connection.readline()
            if line.startswith(b'@stackchan '):
                reply = json.loads(line[11:])
                if reply.get('id') == 191:
                    return reply
        raise RuntimeError('Stack Chan did not answer over USB')
    finally:
        connection.close()


def wait_device(port, mode, timeout=40):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            status = device_request(port, 'status')
            if (status.get('network_mode') == mode and status.get('connected')
                    and status.get('camera_ready')):
                return status
        except (OSError, RuntimeError, json.JSONDecodeError):
            pass
        time.sleep(.5)
    raise RuntimeError(f'Stack Chan did not become ready in {mode} mode')


def camera_status(camera, timeout=3):
    request = urllib.request.Request(
        f"http://{urlsplit(camera['url']).hostname}:81/camera",
        headers={'X-Stream-Key': camera['key']},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def wait_camera(camera, mode, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            status = camera_status(camera)
            if status.get('network_mode') == mode and status.get('wifi_connected'):
                return status
        except (OSError, json.JSONDecodeError):
            pass
        time.sleep(.5)
    raise RuntimeError(f'Camera network did not become ready in {mode} mode')


def join_wifi(device, ssid, password):
    # networksetup supports '-' for password stdin. Secrets never appear in
    # process arguments, output, the recovery state, or benchmark reports.
    result = subprocess.run(
        ['/usr/sbin/networksetup', '-setairportnetwork', device, ssid, '-'],
        input=password + '\n', text=True, capture_output=True, timeout=45, check=False,
    )
    text = (result.stdout + result.stderr).lower()
    if result.returncode or 'error' in text or 'could not' in text or 'failed' in text:
        raise RuntimeError('macOS could not join the requested Wi-Fi network')


def restore_home(root, session):
    """Restore internet before device recovery; always restore the camera config.

    This also runs in a detached watchdog if the test crashes or is terminated.
    The file lock prevents simultaneous parent/watchdog network operations.
    """
    with (session / 'restore.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = json.loads((session / 'state.json').read_text())
        if state.get('restored'):
            return
        home = json.loads((root / '.local/wifi.json').read_text())
        camera = json.loads((session / 'camera-before.json').read_text())
        errors = []
        try:
            join_wifi(state['interface'], home['ssid'], home['password'])
        except (OSError, RuntimeError, subprocess.TimeoutExpired):
            errors.append('Mac home Wi-Fi restoration could not be confirmed')
        try:
            status = device_request(state['port'], 'status')
            if status.get('network_mode') == 'ap':
                result = device_request(state['port'], 'wifi_station')
                if result.get('status') != 'saved':
                    raise RuntimeError('Device rejected station mode')
            status = wait_device(state['port'], 'station')
            camera['url'] = 'http://' + status['ip'] + '/stream'
        except (OSError, RuntimeError, json.JSONDecodeError):
            errors.append('Stack Chan station recovery could not be confirmed; AP lease will expire')
        finally:
            write_private(root / '.local/camera.json', camera)
        state['restored'] = not errors
        state['restore_errors'] = errors
        write_private(session / 'state.json', state)
        if errors:
            raise RuntimeError('; '.join(errors))
        print('Home Wi-Fi and Stack Chan station mode restored.', flush=True)


def run_benchmark(root, seconds, name):
    subprocess.run(
        [sys.executable, '-u', str(root / 'benchmark_camera.py'), '--seconds', str(seconds),
         '--fps', '8', '--quality', '75', '--name', name],
        cwd=root, check=True, timeout=seconds + 60,
    )


def verify_internet(interface):
    route = subprocess.run(['/sbin/route', '-n', 'get', 'default'],
                           capture_output=True, text=True, check=True, timeout=5)
    if f'interface: {interface}' not in route.stdout:
        raise RuntimeError('The requested internet interface is not the default route')
    probe = subprocess.run(
        ['/usr/bin/curl', '--interface', interface, '--connect-timeout', '5', '--max-time', '10',
         '-sS', '-o', '/dev/null', '-w', '%{http_code}', 'https://example.com'],
        capture_output=True, text=True, check=True, timeout=12,
    )
    if probe.stdout != '200':
        raise RuntimeError('Internet HTTPS verification failed')


def run_trial(root, port, interface, seconds, channel, baseline, internet_interface=None, stay=False):
    processes = subprocess.run(['/bin/ps', '-axo', 'command'], capture_output=True,
                               text=True, check=True, timeout=5)
    if 'lego-stackchan-drive run' in processes.stdout:
        raise RuntimeError('Close the camera viewer before starting the single-stream benchmark')
    # Read all local recovery inputs before changing either network.
    home = json.loads((root / '.local/wifi.json').read_text())
    camera = json.loads((root / '.local/camera.json').read_text())
    if not home.get('ssid') or 'password' not in home or not camera.get('key'):
        raise RuntimeError('Private home Wi-Fi and camera configuration are required')
    status = wait_camera(camera, 'station')
    if status.get('firmware') != '0.4.4':
        raise RuntimeError('Install firmware 0.4.4 before the direct-Wi-Fi test')
    if internet_interface:
        verify_internet(internet_interface)
    if stay and not internet_interface:
        raise RuntimeError('--stay requires a verified separate internet interface')
    if baseline:
        print('Collecting the home-Wi-Fi baseline first; keep the scene fixed.', flush=True)
        run_benchmark(root, seconds, 'home-wifi-controlled')
    session = root / '.local/direct-wifi-tests' / time.strftime('%Y%m%d-%H%M%S')
    session.mkdir(parents=True, mode=0o700)
    write_private(session / 'camera-before.json', camera)
    write_private(session / 'state.json', {
        'port': port, 'interface': interface, 'seconds': seconds,
        'channel': channel, 'restored': False, 'internet_interface': internet_interface,
    })
    # Start independent recovery BEFORE the first radio change. No secret
    # credentials are placed on its command line.
    with (session / 'recovery.log').open('a') as recovery_log:
        watchdog = subprocess.Popen(
            [sys.executable, '-u', '-m', 'lego_stackchan_drive.direct_wifi',
             '--root', str(root), '--session', str(session),
             '--restore-after', str(seconds + 150)],
            cwd=root, stdin=subprocess.DEVNULL, stdout=recovery_log,
            stderr=subprocess.STDOUT, start_new_session=True,
        )
    password = secrets.token_urlsafe(18)
    ssid = 'StackChan-Drive-Test'
    keep_direct = False
    try:
        print('Starting Stack Chan AP; ' + ('internet stays on Ethernet.' if internet_interface
                                          else 'internet will pause when the Mac joins.'), flush=True)
        result = device_request(port, 'wifi_ap', ssid=ssid, password=password,
                                channel=channel, lease_seconds=0 if stay else seconds + 120)
        if result.get('status') != 'saved':
            raise RuntimeError('Stack Chan rejected AP mode')
        # Opening the USB status port restarts this board on macOS. A second
        # USB open would consume the one-shot AP and return it to station mode.
        # Only use HTTP readiness after the explicit USB mode-change command.
        time.sleep(3)
        join_wifi(interface, ssid, password)
        if internet_interface:
            verify_internet(internet_interface)
        direct_camera = {**camera, 'url': 'http://192.168.4.1/stream'}
        wait_camera(direct_camera, 'ap')
        write_private(root / '.local/camera.json', direct_camera)
        write_private(root / '.local/direct-wifi.json', {'ssid': ssid, 'password': password,
                                                       'channel': channel})
        print('Collecting direct-Wi-Fi video at 8 FPS/Q75; keep the scene fixed.', flush=True)
        run_benchmark(root, seconds, 'direct-wifi-controlled')
        if internet_interface:
            verify_internet(internet_interface)
        if stay:
            state = json.loads((session / 'state.json').read_text())
            state['kept_direct'] = True
            write_private(session / 'state.json', state)
            keep_direct = True
    finally:
        try:
            if not keep_direct:
                restore_home(root, session)
        except (OSError, RuntimeError, json.JSONDecodeError):
            print('Recovery is incomplete; the detached watchdog remains armed.', flush=True)
            raise
        else:
            watchdog.terminate()
            watchdog.wait(timeout=5)
    print('Direct-Wi-Fi trial finished. ' + ('Camera stays on direct Wi-Fi; internet on Ethernet. '
                                          if keep_direct else '')
          + f'Recovery details: {session / "state.json"}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--port', default='/dev/cu.usbmodem3101')
    parser.add_argument('--interface', default='en0')
    parser.add_argument('--seconds', type=int, default=300)
    parser.add_argument('--channel', type=int, choices=range(1, 12), default=6)
    parser.add_argument('--baseline', action='store_true')
    parser.add_argument('--internet-interface', help='Separate verified internet interface, e.g. en7')
    parser.add_argument('--stay', action='store_true', help='Keep direct Wi-Fi after a successful test')
    parser.add_argument('--run', action='store_true', help='Execute the intentional network test')
    parser.add_argument('--session', type=Path)
    parser.add_argument('--restore-after', type=int)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.restore_after is not None:
        if args.session is None or not 0 <= args.restore_after <= 900:
            parser.error('Recovery requires a session and a bounded delay')
        time.sleep(args.restore_after)
        restore_home(root, args.session)
        return
    if not 20 <= args.seconds <= 600:
        parser.error('Use 20..600 seconds; AP mode is a bounded experiment')
    if not args.run:
        camera = json.loads((root / '.local/camera.json').read_text())
        status = camera_status(camera)
        print(json.dumps(status, indent=2))
        print('Preflight only: Mac Wi-Fi unchanged. --run executes a direct-link test with recovery.')
        return
    # SIGTERM should execute normal recovery; SIGKILL is handled by watchdog.
    def terminate(_signum, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, terminate)
    run_trial(root, args.port, args.interface, args.seconds, args.channel, args.baseline,
              args.internet_interface, args.stay)


if __name__ == '__main__':
    main()
