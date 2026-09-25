"""Native desktop shell for the local Gradio controller."""

from __future__ import annotations

import base64
import os
import subprocess
import sys
import threading
import time
from multiprocessing.connection import Listener
from pathlib import Path

from .bridge import SimulationProxy
from .desktop import activate_mujoco_viewer, controller_window


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
        # Qt's xcb path works for X11 and XWayland and keeps both native
        # windows addressable by the same desktop-layout helper.
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
        "--authkey",
        encoded_key,
        "--robot",
        initial_robot,
    ]
    worker = subprocess.Popen(command)
    proxy: SimulationProxy | None = None
    demo = None
    try:
        connection = listener.accept()
        proxy = SimulationProxy(connection, initial_robot)
        demo, local_url = launch_control_ui(
            proxy,
            inbrowser=False,
            server_port=server_port,
        )
        frame = controller_window()
        window = webview.create_window(
            "Robot Zoo Controller",
            local_url,
            x=frame.x,
            y=frame.y,
            width=frame.width,
            height=frame.height,
            min_size=(350, 620),
            resizable=True,
            on_top=True,
            background_color="#f5f7f8",
            text_select=False,
        )
        shutdown_started = threading.Event()

        def stop_simulation_when_controller_closes() -> None:
            # Cocoa exits its application loop when the final window closes,
            # while Qt can keep the loop alive briefly. Signal the worker from
            # the window event so both backends have the same lifecycle.
            if shutdown_started.is_set():
                return
            shutdown_started.set()
            if proxy is not None:
                proxy.shutdown()

        window.events.closed += stop_simulation_when_controller_closes

        def activate_simulation() -> None:
            time.sleep(0.6)
            activate_mujoco_viewer(worker.pid)

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
        webview.start(
            activate_simulation,
            gui="qt" if sys.platform.startswith("linux") else None,
            debug=False,
            private_mode=True,
        )
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
