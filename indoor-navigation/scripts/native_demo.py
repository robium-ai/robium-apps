#!/usr/bin/env python3
"""Build, run, and stop the isolated native macOS demo."""

from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

try:
    from scripts.native_paths import (
        NativeError,
        NativePaths,
        native_environment,
        read_owned_process,
        require_apple_silicon,
        require_free_ports,
        write_owned_process,
    )
except ModuleNotFoundError:  # direct invocation: python3 scripts/native_demo.py
    from native_paths import (  # type: ignore[no-redef]
        NativeError,
        NativePaths,
        native_environment,
        read_owned_process,
        require_apple_silicon,
        require_free_ports,
        write_owned_process,
    )


RENDERER_FAILURES = (
    'RenderTextureMetalId is not supported by current render engine',
    'Segmentation fault',
)
SCAN_TIMEOUT_SECONDS = 45.0


def _pixi_shell_command(paths: NativePaths, program: str, *arguments: str) -> list[str]:
    return [
        str(paths.pixi), 'run', '--frozen',
        '--manifest-path', str(paths.experiment / 'pixi.toml'),
        'bash', '-c', program, 'native-demo', *arguments,
    ]


def launch_command(paths: NativePaths) -> list[str]:
    return _pixi_shell_command(
        paths,
        'source "$1" && exec ros2 launch indoor_nav_bringup demo.launch.py '
        'gui:=true gateway_script:=$2',
        str(paths.install / 'setup.sh'),
        str(paths.app_root / 'scripts' / 'demo_gateway.py'),
    )


def scan_health_command(paths: NativePaths) -> list[str]:
    return _pixi_shell_command(
        paths,
        'source "$1" && ros2 topic echo /scan --once '
        '--qos-reliability best_effort',
        str(paths.install / 'setup.sh'),
    )


def renderer_failure(line: str) -> bool:
    return (any(message in line for message in RENDERER_FAILURES)
            or ('[gz-' in line and 'process has died' in line))


def build_command(paths: NativePaths) -> list[str]:
    return [
        str(paths.pixi), 'run', '--frozen',
        '--manifest-path', str(paths.experiment / 'pixi.toml'),
        'colcon', '--log-base', str(paths.log), 'build',
        '--base-paths', str(paths.app_root / 'src'),
        '--build-base', str(paths.build),
        '--install-base', str(paths.install),
        '--symlink-install',
    ]


def build_workspace(paths: NativePaths) -> None:
    subprocess.run(
        build_command(paths), cwd=paths.app_root,
        env=native_environment(paths), check=True)


def preflight(paths: NativePaths) -> None:
    require_apple_silicon()
    missing = []
    if not paths.pixi.is_file():
        missing.append('Pixi')
    if not (paths.experiment / '.pixi' / 'envs' / 'default').is_dir():
        missing.append('RoboStack environment')
    if not (paths.viewer / 'index.html').is_file():
        missing.append('Lichtblick viewer')
    if missing:
        raise NativeError(
            f'native setup is incomplete ({", ".join(missing)}); '
            'run make native-setup first')
    if read_owned_process(paths):
        raise NativeError(
            'a native demo from this app is already running; '
            'run make native-down first')
    require_free_ports((8765, 8766))


def wait_for_gateway(port: int, deadline: float, process: subprocess.Popen,
                     renderer_failed: threading.Event) -> None:
    while time.monotonic() < deadline:
        if renderer_failed.is_set():
            raise NativeError('Gazebo renderer initialization failed')
        if process.poll() is not None:
            raise NativeError(
                f'native ROS launch exited during startup ({process.returncode})')
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.25)
        try:
            probe.connect(('127.0.0.1', port))
            return
        except OSError:
            time.sleep(0.25)
        finally:
            probe.close()
    raise NativeError(f'gateway did not listen on port {port} within 30 seconds')


def _process_group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _wait_for_group_exit(pgid: int, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not _process_group_alive(pgid):
            return True
        time.sleep(0.1)
    return not _process_group_alive(pgid)


def stop_owned_process(paths: NativePaths) -> bool:
    owned = read_owned_process(paths)
    if owned is None:
        paths.process_metadata.unlink(missing_ok=True)
        return False
    for requested_signal, wait_seconds in (
        (signal.SIGINT, 15.0),
        (signal.SIGTERM, 5.0),
        (signal.SIGKILL, 1.0),
    ):
        if not _process_group_alive(owned.pgid):
            break
        os.killpg(owned.pgid, requested_signal)
        if _wait_for_group_exit(owned.pgid, wait_seconds):
            break
    paths.process_metadata.unlink(missing_ok=True)
    return True


def _tee_output(process: subprocess.Popen, log_path: Path,
                renderer_failed: threading.Event) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open('w') as log:
        for line in process.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            log.write(line)
            log.flush()
            if renderer_failure(line):
                renderer_failed.set()


def wait_for_scan(paths: NativePaths, process: subprocess.Popen,
                  renderer_failed: threading.Event, deadline: float) -> None:
    """Wait through transient ROS discovery until a real scan arrives."""
    last_detail = 'topic not discovered'
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise NativeError(
                'native ROS launch exited during scan readiness '
                f'({process.returncode})')
        if renderer_failed.is_set():
            raise NativeError('Gazebo renderer initialization failed')
        try:
            result = subprocess.run(
                scan_health_command(paths), cwd=paths.app_root,
                env=native_environment(paths), capture_output=True, text=True,
                timeout=min(5.0, max(0.1, deadline - time.monotonic())),
                check=False)
        except subprocess.TimeoutExpired:
            last_detail = 'scan probe timed out'
            continue
        compact = result.stdout.replace(' ', '')
        if result.returncode == 0 and 'ranges:\n-' in compact:
            return
        last_detail = (result.stderr or result.stdout).strip()[-500:]
        time.sleep(0.25)
    raise NativeError(
        f'/scan did not publish within {SCAN_TIMEOUT_SECONDS:.0f} seconds: '
        f'{last_detail}')


def run_demo(paths: NativePaths) -> int:
    preflight(paths)
    paths.ensure_runtime_directories()
    build_workspace(paths)
    process = subprocess.Popen(
        launch_command(paths), cwd=paths.app_root,
        env=native_environment(paths), stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, bufsize=1,
        start_new_session=True,
    )
    write_owned_process(paths, process.pid, os.getpgid(process.pid))
    renderer_failed = threading.Event()
    output_thread = threading.Thread(
        target=_tee_output,
        args=(process, paths.native_log, renderer_failed),
        daemon=True,
    )
    output_thread.start()
    try:
        wait_for_gateway(8765, time.monotonic() + 30, process, renderer_failed)
        # Use a fresh loopback origin for the robot-camera layout. Lichtblick
        # intentionally restores layouts saved per origin, so keeping localhost
        # here would preserve the pre-camera two-panel layout for existing users.
        url = 'http://127.0.0.1:8765'
        opened = subprocess.run(['/usr/bin/open', url], check=False)
        if opened.returncode != 0:
            print(f'browser did not open automatically; open {url}', file=sys.stderr)
        wait_for_scan(
            paths, process, renderer_failed,
            time.monotonic() + SCAN_TIMEOUT_SECONDS)
        print(f'native demo ready: Gazebo + {url}', flush=True)
        while process.poll() is None:
            if renderer_failed.is_set():
                raise NativeError('Gazebo renderer initialization failed')
            time.sleep(0.25)
        return process.returncode
    except KeyboardInterrupt:
        return 130
    finally:
        if process.poll() is None:
            stop_owned_process(paths)
        paths.process_metadata.unlink(missing_ok=True)
        output_thread.join(timeout=2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('run', 'down'))
    args = parser.parse_args()
    paths = NativePaths.from_app_root(Path(__file__).resolve().parents[1])
    try:
        if args.action == 'down':
            if stop_owned_process(paths):
                print('native demo stopped')
            else:
                print('no owned native demo is running')
            return 0
        return run_demo(paths)
    except (NativeError, subprocess.CalledProcessError) as error:
        print(f'native demo failed: {error}', file=sys.stderr)
        if paths.native_log.exists():
            print(f'log: {paths.native_log}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
