#!/usr/bin/env python3
"""Paths and preflight helpers for the isolated native macOS demo."""

from __future__ import annotations

import json
import os
import platform
import socket
import time
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Mapping, Sequence


class NativeError(RuntimeError):
    """An actionable native-demo setup or preflight failure."""


@dataclass(frozen=True)
class OwnedProcess:
    pid: int
    pgid: int
    app_root: Path
    started_at: float


@dataclass(frozen=True)
class NativePaths:
    app_root: Path
    experiment: Path
    runtime: Path
    pixi_home: Path
    pixi: Path
    cache: Path
    auth: Path
    tmp: Path
    downloads: Path
    viewer: Path
    status: Path
    process_metadata: Path
    runtime_home: Path
    ros_home: Path
    ros_logs: Path
    gz_home: Path
    colcon_home: Path
    build: Path
    install: Path
    log: Path
    native_log: Path

    @classmethod
    def from_app_root(cls, app_root: Path) -> 'NativePaths':
        app_root = app_root.resolve()
        experiment = app_root / 'experiments' / 'native-macos'
        runtime = experiment / 'runtime'
        return cls(
            app_root=app_root,
            experiment=experiment,
            runtime=runtime,
            pixi_home=runtime / 'pixi',
            pixi=runtime / 'pixi' / 'bin' / 'pixi',
            cache=runtime / 'cache',
            auth=runtime / 'auth' / 'auth.json',
            tmp=runtime / 'tmp',
            downloads=runtime / 'downloads',
            viewer=runtime / 'viewer',
            status=runtime / 'demo_status.json',
            process_metadata=runtime / 'native-demo.json',
            runtime_home=runtime / 'home',
            ros_home=runtime / 'ros',
            ros_logs=runtime / 'logs' / 'ros',
            gz_home=runtime / 'gazebo',
            colcon_home=runtime / 'colcon',
            build=experiment / 'build',
            install=experiment / 'install',
            log=experiment / 'log',
            native_log=runtime / 'logs' / 'native-demo.log',
        )

    def runtime_paths(self) -> tuple[Path, ...]:
        excluded = {'app_root', 'experiment', 'build', 'install', 'log'}
        return tuple(
            getattr(self, item.name)
            for item in fields(self)
            if item.name not in excluded
        )

    def ensure_runtime_directories(self) -> None:
        for path in (
            self.pixi.parent,
            self.cache,
            self.auth.parent,
            self.tmp,
            self.downloads,
            self.runtime_home,
            self.ros_home,
            self.ros_logs,
            self.gz_home,
            self.colcon_home,
            self.native_log.parent,
            self.build,
            self.install,
            self.log,
        ):
            path.mkdir(parents=True, exist_ok=True)


def native_environment(
    paths: NativePaths, base: Mapping[str, str] | None = None,
) -> dict[str, str]:
    env = dict(os.environ if base is None else base)
    secret_suffixes = ('_TOKEN', '_SECRET', '_PASSWORD', '_API_KEY')
    for name in tuple(env):
        if name.upper().endswith(secret_suffixes):
            env.pop(name)
    env.update({
        'PIXI_HOME': str(paths.pixi_home),
        'PIXI_CACHE_DIR': str(paths.cache),
        'RATTLER_CACHE_DIR': str(paths.cache),
        'TMPDIR': str(paths.tmp),
        # Gazebo's GZ_HOMEDIR is a compile-time alias for HOME, not a
        # configurable directory. Scope HOME only for native child processes
        # so Gazebo cannot write ~/.gz on the host.
        'HOME': str(paths.runtime_home),
        'ROS_HOME': str(paths.ros_home),
        'ROS_LOG_DIR': str(paths.ros_logs),
        'GZ_HOMEDIR': str(paths.gz_home),
        'COLCON_HOME': str(paths.colcon_home),
        'DEMO_STATUS_PATH': str(paths.status),
        'DEMO_STATIC_ROOT': str(paths.viewer),
        'DEMO_SHUTDOWN_MODE': 'parent',
        'RMW_IMPLEMENTATION': 'rmw_cyclonedds_cpp',
        'ROS_DOMAIN_ID': '42',
        'TURTLEBOT3_MODEL': 'waffle_pi',
    })
    return env


def require_apple_silicon() -> None:
    system = platform.system()
    machine = platform.machine()
    if system != 'Darwin' or machine != 'arm64':
        raise NativeError(
            f'native mode requires macOS arm64 (found {system} {machine}); '
            'use make demo for the portable Docker path')


def require_free_ports(ports: Sequence[int]) -> None:
    for port in ports:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            # Match the bridge/gateway server behavior: a connection from a
            # just-stopped run may remain in TIME_WAIT, but that is not an
            # active listener and must not block an immediate restart.
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(('127.0.0.1', port))
        except OSError as error:
            raise NativeError(f'port {port} is already in use') from error
        finally:
            probe.close()


def read_owned_process(paths: NativePaths) -> OwnedProcess | None:
    try:
        raw = json.loads(paths.process_metadata.read_text())
        owned = OwnedProcess(
            pid=int(raw['pid']),
            pgid=int(raw['pgid']),
            app_root=Path(raw['app_root']).resolve(),
            started_at=float(raw['started_at']),
        )
        if owned.pid <= 1 or owned.pgid <= 1:
            return None
        if owned.app_root != paths.app_root.resolve():
            return None
        os.kill(owned.pid, 0)
        return owned
    except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError,
            ValueError, OSError):
        return None


def write_owned_process(paths: NativePaths, pid: int, pgid: int | None = None) -> None:
    paths.runtime.mkdir(parents=True, exist_ok=True)
    record = {
        'pid': pid,
        'pgid': pid if pgid is None else pgid,
        'app_root': str(paths.app_root.resolve()),
        'started_at': time.time(),
    }
    temporary = paths.process_metadata.with_suffix('.tmp')
    temporary.write_text(json.dumps(record))
    os.replace(temporary, paths.process_metadata)
