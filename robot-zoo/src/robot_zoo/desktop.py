"""Desktop helpers for tiling the two native application surfaces."""

from __future__ import annotations

import os
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any


CONTROLLER_WIDTH = 390
WINDOW_GAP = 12


@dataclass(frozen=True)
class ControllerWindow:
    x: int | None
    y: int | None
    width: int
    height: int


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


def controller_window() -> ControllerWindow:
    """Return a slim right-side controller frame for the current desktop."""
    if sys.platform.startswith("linux"):
        area = _linux_work_area()
        if area is None:
            return ControllerWindow(None, None, CONTROLLER_WIDTH, 820)
        x, y, width, height = area
        return ControllerWindow(
            x + width - CONTROLLER_WIDTH,
            y,
            CONTROLLER_WIDTH,
            height,
        )
    if sys.platform != "darwin":
        return ControllerWindow(None, None, CONTROLLER_WIDTH, 820)

    from AppKit import NSScreen

    screen = NSScreen.mainScreen()
    frame = screen.frame()
    visible = screen.visibleFrame()
    x = round(visible.origin.x + visible.size.width - CONTROLLER_WIDTH)
    y = round(frame.size.height - visible.origin.y - visible.size.height)
    return ControllerWindow(x, y, CONTROLLER_WIDTH, round(visible.size.height))


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


def _linux_focus_and_keys(pid: int, shortcuts: tuple[str, ...] = ()) -> bool:
    try:
        from Xlib import X, XK, display
        from Xlib.ext import xtest

        connection = display.Display()
        window = None
        for _ in range(40):
            window = _linux_mujoco_window(connection, pid)
            if window is not None:
                break
            time.sleep(0.05)
        if window is None:
            connection.close()
            return False
        window.raise_window()
        window.set_input_focus(X.RevertToParent, X.CurrentTime)
        connection.sync()
        if shortcuts:
            alt = connection.keysym_to_keycode(XK.string_to_keysym("Alt_L"))
            xtest.fake_input(connection, X.KeyPress, alt)
            for key in shortcuts:
                keycode = connection.keysym_to_keycode(XK.string_to_keysym(key))
                xtest.fake_input(connection, X.KeyPress, keycode)
                xtest.fake_input(connection, X.KeyRelease, keycode)
                connection.sync()
                time.sleep(0.04)
            xtest.fake_input(connection, X.KeyRelease, alt)
            connection.sync()
        connection.close()
        return True
    except Exception as error:
        print(f"Robot Zoo desktop warning: {error}", file=sys.stderr, flush=True)
        return False


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
            x=x,
            y=y,
            width=max(720, width - CONTROLLER_WIDTH - WINDOW_GAP),
            height=height,
        )
        connection.sync()
        connection.close()
        # File, Option, and Simulation begin open. Toggle those closed, then
        # toggle Rendering and Joint open using MuJoCo's native shortcuts.
        _linux_focus_and_keys(os.getpid(), ("f", "o", "s", "r", "j"))
    except Exception as error:
        print(f"Robot Zoo desktop warning: {error}", file=sys.stderr, flush=True)


def activate_mujoco_viewer(pid: int) -> None:
    """Bring the MuJoCo worker window forward after both surfaces open."""
    if sys.platform.startswith("linux"):
        _linux_focus_and_keys(pid)
        return
    if sys.platform != "darwin":
        return
    from AppKit import (
        NSApplicationActivateAllWindows,
        NSApplicationActivateIgnoringOtherApps,
        NSRunningApplication,
    )
    import Quartz

    application = None
    for _ in range(40):
        application = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
        windows = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly,
            Quartz.kCGNullWindowID,
        )
        if application is not None and any(
            int(window.get("kCGWindowOwnerPID", -1)) == pid
            and str(window.get("kCGWindowName") or "").startswith("MuJoCo")
            for window in windows
        ):
            break
        time.sleep(0.05)
    if application is not None:
        application.activateWithOptions_(
            NSApplicationActivateAllWindows | NSApplicationActivateIgnoringOtherApps
        )


def configure_mujoco_viewer() -> None:
    """Tile MuJoCo left and open only Rendering and Joint sections."""
    if sys.platform.startswith("linux"):
        threading.Thread(
            target=_configure_linux_mujoco_viewer,
            name="mujoco-default-ui",
            daemon=True,
        ).start()
        return
    if sys.platform != "darwin":
        return

    from AppKit import NSApplication, NSMakeRect, NSScreen
    from PyObjCTools import AppHelper

    def tile_window() -> None:
        screen = NSScreen.mainScreen()
        visible = screen.visibleFrame()
        width = max(
            720,
            round(visible.size.width - CONTROLLER_WIDTH - WINDOW_GAP),
        )
        frame = NSMakeRect(
            visible.origin.x,
            visible.origin.y,
            width,
            visible.size.height,
        )
        for window in NSApplication.sharedApplication().windows():
            if str(window.title()).startswith("MuJoCo"):
                window.setFrame_display_(frame, True)

    def keep_layout_applied() -> None:
        # A reload destroys one GLFW window and creates another. Schedule the
        # same main-thread layout a few times so the newly mapped Cocoa window
        # is caught after both first launch and robot switching.
        for delay in (0.0, 0.2, 0.6, 1.0):
            time.sleep(delay)
            AppHelper.callAfter(tile_window)

    threading.Thread(
        target=keep_layout_applied,
        name="mujoco-window-layout",
        daemon=True,
    ).start()

    def set_default_sections() -> None:
        # Simulate starts File, Option, and Simulation open. Rendering and Joint
        # start closed. These are the native section shortcuts defined by MuJoCo.
        time.sleep(0.55)
        import Quartz

        option_keycode = 58
        option_down = Quartz.CGEventCreateKeyboardEvent(
            None, option_keycode, True
        )
        Quartz.CGEventSetFlags(
            option_down, Quartz.kCGEventFlagMaskAlternate
        )
        Quartz.CGEventPostToPid(os.getpid(), option_down)
        time.sleep(0.08)
        for keycode in (3, 31, 1, 15, 38):  # Option-F/O/S/R/J
            down = Quartz.CGEventCreateKeyboardEvent(None, keycode, True)
            Quartz.CGEventSetFlags(down, Quartz.kCGEventFlagMaskAlternate)
            Quartz.CGEventPostToPid(os.getpid(), down)
            up = Quartz.CGEventCreateKeyboardEvent(None, keycode, False)
            Quartz.CGEventSetFlags(up, Quartz.kCGEventFlagMaskAlternate)
            Quartz.CGEventPostToPid(os.getpid(), up)
            time.sleep(0.04)
        option_up = Quartz.CGEventCreateKeyboardEvent(
            None, option_keycode, False
        )
        Quartz.CGEventPostToPid(os.getpid(), option_up)

    threading.Thread(
        target=set_default_sections,
        name="mujoco-default-ui",
        daemon=True,
    ).start()
