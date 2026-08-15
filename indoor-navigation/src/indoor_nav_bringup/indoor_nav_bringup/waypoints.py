"""Validated, per-map waypoint persistence and robot-side operations."""

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import re


NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')


@dataclass(frozen=True)
class Waypoint:
    x: float
    y: float
    yaw: float


class WaypointStore:
    """Persist named poses in a versioned sidecar beside one saved map."""

    def __init__(self, maps_root):
        self._maps_root = Path(maps_root)

    def list_names(self, world, map_name):
        path = self._path(world, map_name)
        return sorted(self._load(path))

    def save(self, world, map_name, name, waypoint):
        waypoint_name = self._validate_name(name)
        pose = self._validate_waypoint(waypoint)
        path = self._path(world, map_name)
        waypoints = self._load(path)
        if waypoint_name in waypoints:
            raise ValueError(f'waypoint {waypoint_name!r} already exists')
        waypoints[waypoint_name] = pose
        self._write(path, waypoints)

    def get(self, world, map_name, name):
        waypoint_name = self._validate_name(name)
        waypoints = self._load(self._path(world, map_name))
        try:
            return waypoints[waypoint_name]
        except KeyError:
            raise KeyError(f'waypoint {waypoint_name!r} not found') from None

    def delete(self, world, map_name, name):
        waypoint_name = self._validate_name(name)
        path = self._path(world, map_name)
        waypoints = self._load(path)
        if waypoint_name not in waypoints:
            raise KeyError(f'waypoint {waypoint_name!r} not found')
        del waypoints[waypoint_name]
        if waypoints:
            self._write(path, waypoints)
        else:
            path.unlink()

    def _path(self, world, map_name):
        world_name = self._validate_name(world)
        selected_map = self._validate_name(map_name)
        return self._maps_root / world_name / f'{selected_map}.waypoints.json'

    @staticmethod
    def _validate_name(name):
        if not isinstance(name, str) or NAME.fullmatch(name) is None:
            raise ValueError(
                'name must use 1-64 letters, numbers, dashes, or underscores')
        return name

    @staticmethod
    def _validate_waypoint(waypoint):
        if not isinstance(waypoint, Waypoint):
            raise ValueError('waypoint must be a Waypoint')
        values = (waypoint.x, waypoint.y, waypoint.yaw)
        if any(isinstance(value, bool) or not isinstance(value, (int, float))
               or not math.isfinite(value) for value in values):
            raise ValueError('waypoint coordinates must be finite numbers')
        return Waypoint(*(float(value) for value in values))

    def _load(self, path):
        if not path.exists():
            return {}
        try:
            document = json.loads(path.read_text(encoding='utf-8'))
            if (not isinstance(document, dict)
                    or set(document) != {'version', 'waypoints'}
                    or document['version'] != 1
                    or not isinstance(document['waypoints'], dict)):
                raise ValueError('invalid document shape')
            waypoints = {}
            for name, raw in document['waypoints'].items():
                waypoint_name = self._validate_name(name)
                if not isinstance(raw, dict) or set(raw) != {'x', 'y', 'yaw'}:
                    raise ValueError(f'invalid waypoint {name!r}')
                waypoints[waypoint_name] = self._validate_waypoint(
                    Waypoint(raw['x'], raw['y'], raw['yaw']))
            return waypoints
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(f'invalid waypoint sidecar {path}: {exc}') from exc

    @staticmethod
    def _write(path, waypoints):
        document = {
            'version': 1,
            'waypoints': {
                name: {'x': pose.x, 'y': pose.y, 'yaw': pose.yaw}
                for name, pose in sorted(waypoints.items())
            },
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + '.tmp')
        try:
            temporary.write_text(
                json.dumps(document, indent=2, sort_keys=True) + '\n',
                encoding='utf-8',
            )
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


class WaypointController:
    """Apply session-mode rules around storage, TF capture, and goal output."""

    def __init__(self, store, context, lookup_pose, publish_goal):
        self._store = store
        self._context = context
        self._lookup_pose = lookup_pose
        self._publish_goal = publish_goal

    def names(self):
        world, map_name = self._scope()
        return self._store.list_names(world, map_name)

    def save(self, name):
        world, map_name = self._scope()
        waypoint = self._lookup_pose()
        self._store.save(world, map_name, name, waypoint)
        return f'saved waypoint {name!r} at the robot current position'

    def navigate(self, name):
        world, map_name = self._scope()
        waypoint = self._store.get(world, map_name, name)
        self._publish_goal(waypoint)
        return f'navigation requested to waypoint {name!r}'

    def delete(self, name):
        world, map_name = self._scope()
        self._store.delete(world, map_name, name)
        return f'deleted waypoint {name!r}'

    def _scope(self):
        mode, world, map_name = self._context()
        if mode != 'LOCALIZATION' or not map_name:
            raise RuntimeError(
                'waypoint actions require an active LOCALIZATION session')
        return world, map_name
