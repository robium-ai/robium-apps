"""Tiny local command bridge between the controller and MuJoCo processes."""

from __future__ import annotations

import threading
from multiprocessing.connection import Connection
from typing import Any

from .controllers import ROBOTS
from .simulation import SimulationManager


class SimulationProxy:
    """Expose the UI-facing SimulationManager API over one local connection."""

    def __init__(self, connection: Connection, initial_robot: str):
        self._connection = connection
        self._lock = threading.Lock()
        self._initial_robot = self._resolve_robot(initial_robot)

    @staticmethod
    def _resolve_robot(robot: str) -> str:
        normalized = robot.strip().casefold()
        for key, info in ROBOTS.items():
            if normalized in {key.casefold(), info.label.casefold()}:
                return key
        raise ValueError(f"unknown robot: {robot}")

    @property
    def robot_choices(self) -> tuple[str, ...]:
        return tuple(info.label for info in ROBOTS.values())

    @property
    def initial_robot_label(self) -> str:
        return ROBOTS[self._initial_robot].label

    def actions_for(self, robot: str) -> tuple[str, ...]:
        return ROBOTS[self._resolve_robot(robot)].actions

    def _call(self, method: str, *args: Any) -> Any:
        with self._lock:
            self._connection.send({"method": method, "args": args})
            response = self._connection.recv()
        if not response["ok"]:
            raise RuntimeError(response["error"])
        return response.get("result")

    def load_robot(self, robot: str) -> str:
        return self._call("load_robot", robot)

    def move(self, vx: float, wz: float) -> str:
        return self._call("move", vx, wz)

    def stop(self) -> str:
        return self._call("stop")

    def set_speed(self, speed: float) -> str:
        return self._call("set_speed", speed)

    def reset(self) -> str:
        return self._call("reset")

    def action(self, name: str) -> str:
        return self._call("action", name)

    def shutdown(self) -> None:
        try:
            self._call("shutdown")
        except (BrokenPipeError, EOFError, OSError):
            pass
        finally:
            self._connection.close()


def serve_commands(manager: SimulationManager, connection: Connection) -> None:
    """Apply serialized UI commands to a thread-safe SimulationManager."""
    allowed = {
        "load_robot",
        "move",
        "stop",
        "set_speed",
        "reset",
        "action",
        "shutdown",
    }
    try:
        while not manager.snapshot().shutdown:
            request = connection.recv()
            method = request.get("method")
            args = request.get("args", ())
            if method not in allowed:
                response = {"ok": False, "error": f"unsupported command: {method}"}
            else:
                try:
                    result = getattr(manager, method)(*args)
                    response = {"ok": True, "result": result}
                except Exception as exc:  # Return callback errors to the UI.
                    response = {"ok": False, "error": str(exc)}
            connection.send(response)
    except (BrokenPipeError, EOFError, OSError):
        manager.shutdown()
    finally:
        connection.close()
