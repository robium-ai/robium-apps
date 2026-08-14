"""Process-level state machine for interactive simulation and navigation sessions."""

from pathlib import Path
import re


WORLD_NAMES = (
    'furnished_house',
    'tugbot_warehouse',
)
MAP_NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')


class SessionProcesses:
    """Own one simulator and at most one mapping/localization child process."""

    def __init__(self, process_factory, maps_root, initial_world='furnished_house'):
        self._factory = process_factory
        self._maps_root = Path(maps_root)
        self._simulation = None
        self._navigation = None
        self._map_name = None
        self.mode = 'IDLE'
        self.world = self._validate_world(initial_world)
        self._start_simulation()

    def start_mapping(self, map_name):
        name = self._validate_map_name(map_name)
        self._stop_navigation()
        map_dir = self._world_maps()
        map_dir.mkdir(parents=True, exist_ok=True)
        self._navigation = self._factory(
            'navigation',
            self._navigation_command('mapping'),
        )
        self._map_name = name
        self.mode = 'MAPPING'

    def stop_mapping(self, save):
        if self.mode != 'MAPPING' or self._map_name is None:
            raise RuntimeError('stop mapping requires an active mapping session')
        path = self._world_maps() / self._map_name
        save(path)
        self._stop_navigation()
        return path

    def load_map(self, map_name):
        name = self._validate_map_name(map_name)
        path = self._world_maps() / f'{name}.yaml'
        if not path.is_file():
            raise FileNotFoundError(f'map {name!r} is missing for world {self.world!r}')
        self._stop_navigation()
        self._navigation = self._factory(
            'navigation',
            self._navigation_command('localization', path),
        )
        self._map_name = name
        self.mode = 'LOCALIZATION'

    def restart_simulation(self, world):
        next_world = self._validate_world(world)
        self._stop_navigation()
        if self._simulation is not None:
            self._simulation.stop()
        self.world = next_world
        self._start_simulation()

    def available_maps(self):
        try:
            return sorted(path.stem for path in self._world_maps().glob('*.yaml'))
        except OSError:
            return []

    def close(self):
        self._stop_navigation()
        if self._simulation is not None:
            self._simulation.stop()
            self._simulation = None

    def _world_maps(self):
        return self._maps_root / self.world

    def _start_simulation(self):
        self._simulation = self._factory(
            'simulation',
            [
                'ros2', 'launch', 'indoor_nav_bringup', 'sim.launch.py',
                f'world:={self.world}', 'bridge:=false',
            ],
        )

    def _stop_navigation(self):
        if self._navigation is not None:
            self._navigation.stop()
            self._navigation = None
        self._map_name = None
        self.mode = 'IDLE'

    @staticmethod
    def _navigation_command(mode, map_yaml=None):
        command = [
            'ros2', 'launch', 'indoor_nav_bringup', 'navigation_stack.launch.py',
            f'mode:={mode}',
        ]
        if map_yaml is not None:
            command.append(f'map_yaml:={map_yaml}')
        return command

    @staticmethod
    def _validate_world(world):
        if world not in WORLD_NAMES:
            raise ValueError(f'unknown world {world!r}; choose one of {WORLD_NAMES}')
        return world

    @staticmethod
    def _validate_map_name(name):
        if not isinstance(name, str) or MAP_NAME.fullmatch(name) is None:
            raise ValueError('map name must use 1-64 letters, numbers, dashes, or underscores')
        return name
