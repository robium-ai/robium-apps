"""Native desktop shell for the local Gradio controller."""

from __future__ import annotations

import base64
import os
import subprocess
import sys
import threading
from multiprocessing.connection import Listener
from pathlib import Path

from .bridge import SimulationProxy
from .desktop import (CONTROLLER_MIN_SIZE, ControllerWindow, controller_window, save_controller_window)


def _mjpython_executable() -> Path:
    candidate = Path(sys.executable).with_name("mjpython")
    if sys.platform == "darwin" and candidate.exists():
        return candidate
    return Path(sys.executable)


def run_native_application(
    initial_robot: str,
    *,
    server_port: int | None = None,
) -> int:
    """Open Gradio inside a native window and MuJoCo in a worker process."""
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
    import webview

    from .gradio_ui import launch_control_ui

    authkey = os.urandom(32)
    listener = Listener(("127.0.0.1", 0), authkey=authkey)
    host, port = listener.address
    encoded_key = base64.urlsafe_b64encode(authkey).decode("ascii")
    command = [
        str(_mjpython_executable()),
        "-m",
        "robot_zoo",
        "worker",
        "--host",
        host,
        "--port",
        str(port),
        f"--authkey={encoded_key}",
        "--robot",
        initial_robot,
    ]
    worker = subprocess.Popen(command)
    proxy: SimulationProxy | None = None
    demo = None
    try:
        connection = listener.accept()
        proxy = SimulationProxy(connection, initial_robot)
        window = None

        def set_pinned(pinned: bool) -> None:
            if window is not None:
                window.on_top = pinned

        demo, local_url = launch_control_ui(
            proxy,
            inbrowser=False,
            server_port=server_port,
            on_pin=set_pinned,
        )
        frame = controller_window()
        window = webview.create_window(
            "Robot Zoo Controller",
            local_url,
            x=frame.x,
            y=frame.y,
            width=frame.width,
            height=frame.height,
            min_size=CONTROLLER_MIN_SIZE,
            resizable=True,
            on_top=True,
            background_color="#232a31",
            text_select=False,
        )

        geometry = {"x": frame.x, "y": frame.y, "width": frame.width, "height": frame.height}
        geometry_lock = threading.Lock()

        def moved(x, y):
            with geometry_lock:
                geometry.update(x=round(x), y=round(y))

        def resized(width, height):
            with geometry_lock:
                geometry.update(width=round(width), height=round(height))

        def save_geometry():
            with geometry_lock:
                save_controller_window(ControllerWindow(**geometry))

        window.events.moved += moved
        window.events.resized += resized
        window.events.closed += save_geometry
        shutdown_started = threading.Event()

        def stop_simulation_when_controller_closes():
            if not shutdown_started.is_set():
                shutdown_started.set()
                proxy.shutdown()

        window.events.closed += stop_simulation_when_controller_closes

        def close_controller_when_simulation_exits() -> None:
            worker.wait()
            try:
                window.destroy()
            except Exception:
                pass

        threading.Thread(
            target=close_controller_when_simulation_exits,
            name="simulation-monitor",
            daemon=True,
        ).start()
        webview.start(gui="qt" if sys.platform.startswith("linux") else None, debug=False, private_mode=True)
        return worker.returncode or 0
    finally:
        if proxy is not None:
            proxy.shutdown()
        if demo is not None:
            demo.close()
        listener.close()
        if worker.poll() is None:
            try:
                worker.wait(timeout=5)
            except subprocess.TimeoutExpired:
                worker.terminate()
                worker.wait(timeout=5)
