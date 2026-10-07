"""Small macOS window helpers for the two native application surfaces."""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


CONTROLLER_WIDTH = 560
CONTROLLER_HEIGHT = 440
CONTROLLER_MIN_SIZE = (560, 440)
WINDOW_GAP = 24
WINDOW_STATE = Path.home() / ".config" / "robot-zoo" / "window.json"


@dataclass(frozen=True)
class ControllerWindow:
    x: int | None
    y: int | None
    width: int
    height: int


def controller_window(state_path: Path = WINDOW_STATE) -> ControllerWindow:
    """Restore a floating controller, clamped to the current display."""
    bounds = None
    if sys.platform == "darwin":
        from AppKit import NSScreen
        screen = NSScreen.mainScreen()
        frame, visible = screen.frame(), screen.visibleFrame()
        bounds = (round(visible.origin.x),
                  round(frame.size.height - visible.origin.y - visible.size.height),
                  round(visible.size.width), round(visible.size.height))
    elif sys.platform.startswith("linux"):
        bounds = _linux_work_area()
    saved = {}
    try:
        candidate = json.loads(state_path.read_text())
        if isinstance(candidate, dict):
            saved = {key: value for key, value in candidate.items()
                     if key in {"x", "y", "width", "height"} and type(value) is int}
    except (OSError, ValueError):
        pass
    width = max(CONTROLLER_MIN_SIZE[0], saved.get("width", CONTROLLER_WIDTH))
    height = max(CONTROLLER_MIN_SIZE[1], saved.get("height", CONTROLLER_HEIGHT))
    x, y = saved.get("x"), saved.get("y")
    if bounds:
        left, top, available_width, available_height = bounds
        width, height = min(width, available_width), min(height, available_height)
        x = min(max(left, x if x is not None else left + available_width - width - WINDOW_GAP), left + available_width - width)
        y = min(max(top, y if y is not None else top + available_height - height - WINDOW_GAP), top + available_height - height)
    return ControllerWindow(x, y, width, height)


def save_controller_window(frame: ControllerWindow, state_path: Path = WINDOW_STATE) -> None:
    """Keep window preferences separate from application source."""
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(frame)))
        temporary.replace(state_path)
    except OSError:
        pass  # A read-only preferences directory must not prevent closing.


def configure_mujoco_viewer() -> None:
    """Use the display for simulation; the controller floats independently."""
    if sys.platform.startswith("linux"):
        threading.Thread(target=_configure_linux_mujoco_viewer, daemon=True).start()
        return
    if sys.platform != "darwin":
        return

    from AppKit import NSApplication, NSMakeRect, NSScreen
    from PyObjCTools import AppHelper

    def tile_window() -> None:
        screen = NSScreen.mainScreen()
        visible = screen.visibleFrame()
        width = round(visible.size.width - 2 * WINDOW_GAP)
        frame = NSMakeRect(
            visible.origin.x + WINDOW_GAP,
            visible.origin.y + WINDOW_GAP,
            width,
            visible.size.height - 2 * WINDOW_GAP,
        )
        for window in NSApplication.sharedApplication().windows():
            if str(window.title()).startswith("MuJoCo"):
                window.setFrame_display_(frame, True)

    AppHelper.callAfter(tile_window)


def _linux_work_area() -> tuple[int, int, int, int] | None:
    """Read the current X11 desktop work area, including under XWayland."""
    try:
        from Xlib import X, display

        connection = display.Display()
        root = connection.screen().root
        current = root.get_full_property(
            connection.intern_atom("_NET_CURRENT_DESKTOP"), X.AnyPropertyType
        )
        desktop = int(current.value[0]) if current is not None else 0
        work_area = root.get_full_property(
            connection.intern_atom("_NET_WORKAREA"), X.AnyPropertyType
        )
        if work_area is not None and len(work_area.value) >= (desktop + 1) * 4:
            offset = desktop * 4
            result = tuple(int(value) for value in work_area.value[offset : offset + 4])
        else:
            screen = connection.screen()
            result = (0, 0, screen.width_in_pixels, screen.height_in_pixels)
        connection.close()
        return result
    except Exception:
        return None


def _linux_mujoco_window(connection: Any, pid: int) -> Any | None:
    """Find the MuJoCo X11 client owned by this worker process."""
    from Xlib import X

    root = connection.screen().root
    clients = root.get_full_property(
        connection.intern_atom("_NET_CLIENT_LIST"), X.AnyPropertyType
    )
    windows = (
        [connection.create_resource_object("window", int(w)) for w in clients.value]
        if clients is not None
        else list(root.query_tree().children)
    )
    pid_atom = connection.intern_atom("_NET_WM_PID")
    utf8 = connection.intern_atom("UTF8_STRING")
    name_atom = connection.intern_atom("_NET_WM_NAME")
    for window in windows:
        try:
            window_pid = window.get_full_property(pid_atom, X.AnyPropertyType)
            name = window.get_full_property(name_atom, utf8)
            title = (
                bytes(name.value).decode("utf-8", errors="replace")
                if name is not None
                else str(window.get_wm_name() or "")
            )
            if title.startswith("MuJoCo") and (
                window_pid is None or int(window_pid.value[0]) == pid
            ):
                return window
        except Exception:
            continue
    return None


def _configure_linux_mujoco_viewer() -> None:
    try:
        from Xlib import display

        connection = display.Display()
        window = None
        for _ in range(40):
            window = _linux_mujoco_window(connection, os.getpid())
            if window is not None:
                break
            time.sleep(0.05)
        area = _linux_work_area()
        if window is None or area is None:
            connection.close()
            return
        x, y, width, height = area
        window.configure(
            x=x + WINDOW_GAP,
            y=y + WINDOW_GAP,
            width=max(1, width - 2 * WINDOW_GAP),
            height=max(1, height - 2 * WINDOW_GAP),
        )
        connection.sync()
        connection.close()
    except Exception as error:
        print(f"Robot Zoo desktop warning: {error}", file=sys.stderr, flush=True)
