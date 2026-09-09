#!/usr/bin/env python3
"""Small DepthAI RGB camera server for the offboard OAK-D.

The server intentionally exposes a narrow HTTP surface:

* ``/health`` reports whether a fresh frame is available.
* ``/frame.jpg`` returns the latest JPEG for Gemini scene input.
* ``/stream`` returns an MJPEG stream for the browser console.
"""

from __future__ import annotations

import json
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import depthai as dai


FRAME_STALE_S = 3.0


class CameraState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frame: bytes | None = None
        self._captured_at = 0.0
        self._error = "camera is starting"

    def update(self, frame: bytes) -> None:
        with self._lock:
            self._frame = frame
            self._captured_at = time.monotonic()
            self._error = ""

    def fail(self, message: str) -> None:
        with self._lock:
            self._error = message

    def snapshot(self) -> tuple[bytes | None, float | None, str]:
        with self._lock:
            frame = self._frame
            captured_at = self._captured_at
            error = self._error
        age_s = None if frame is None else time.monotonic() - captured_at
        if age_s is not None and age_s > FRAME_STALE_S:
            return None, age_s, error or "camera frame is stale"
        return frame, age_s, error


def capture_frames(state: CameraState, width: int, height: int, fps: float) -> None:
    while True:
        try:
            # This is an RVC2 OAK-D. DepthAI 2's ColorCamera path is retained
            # deliberately: DepthAI 3.10 detected this unit but failed while
            # booting its MyriadX firmware on the Jetson, whereas 2.33 produced
            # a real frame on the same USB connection.
            pipeline = dai.Pipeline()
            camera = pipeline.create(dai.node.ColorCamera)
            camera.setBoardSocket(dai.CameraBoardSocket.CAM_A)
            camera.setPreviewSize(width, height)
            camera.setInterleaved(False)
            camera.setColorOrder(dai.ColorCameraProperties.ColorOrder.BGR)
            camera.setFps(fps)
            output = pipeline.create(dai.node.XLinkOut)
            output.setStreamName("rgb")
            camera.preview.link(output.input)
            # This OAK-D/Jetson pairing enumerates at SuperSpeed but loses the
            # device during firmware boot. High Speed is reliable and still
            # easily carries the 640x360/12 fps contest stream.
            with dai.Device(pipeline, maxUsbSpeed=dai.UsbSpeed.HIGH) as device:
                queue = device.getOutputQueue("rgb", maxSize=1, blocking=False)
                print(
                    f"OAK-D RGB capture ready: {width}x{height} at {fps:g} fps",
                    flush=True,
                )
                while True:
                    image = queue.get()
                    ok, encoded = cv2.imencode(
                        ".jpg",
                        image.getCvFrame(),
                        [cv2.IMWRITE_JPEG_QUALITY, 82],
                    )
                    if ok:
                        state.update(encoded.tobytes())
        except Exception as error:  # noqa: BLE001 - camera must retry after USB resets.
            message = f"DepthAI capture failed: {error}"
            state.fail(message)
            print(message, flush=True)
            time.sleep(3.0)


def make_handler(state: CameraState):
    class Handler(BaseHTTPRequestHandler):
        def _write_json(self, payload: dict, status: int = HTTPStatus.OK) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            frame, age_s, error = state.snapshot()
            if self.path == "/health":
                self._write_json(
                    {
                        "status": "ok" if frame is not None else "starting",
                        "fresh": frame is not None,
                        "age_s": None if age_s is None else round(age_s, 3),
                        "error": error,
                    },
                    HTTPStatus.OK if frame is not None else HTTPStatus.SERVICE_UNAVAILABLE,
                )
                return
            if self.path == "/frame.jpg":
                if frame is None:
                    self._write_json(
                        {"status": "starting", "reason": error},
                        HTTPStatus.SERVICE_UNAVAILABLE,
                    )
                    return
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(frame)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(frame)
                return
            if self.path == "/stream":
                self.send_response(HTTPStatus.OK)
                self.send_header(
                    "Content-Type", "multipart/x-mixed-replace; boundary=frame"
                )
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                try:
                    while True:
                        frame, _, _ = state.snapshot()
                        if frame is not None:
                            self.wfile.write(b"--frame\r\n")
                            self.wfile.write(b"Content-Type: image/jpeg\r\n")
                            self.wfile.write(
                                f"Content-Length: {len(frame)}\r\n\r\n".encode()
                            )
                            self.wfile.write(frame)
                            self.wfile.write(b"\r\n")
                            self.wfile.flush()
                        time.sleep(0.1)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                return
            self._write_json(
                {"status": "not_found"}, HTTPStatus.NOT_FOUND
            )

        def log_message(self, _format: str, *_args) -> None:
            return

    return Handler


def main() -> None:
    state = CameraState()
    capture = threading.Thread(
        target=capture_frames,
        args=(state, 640, 360, 12.0),
        daemon=True,
    )
    capture.start()
    server = ThreadingHTTPServer(("0.0.0.0", 8081), make_handler(state))
    print("OAK-D HTTP server: http://0.0.0.0:8081", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
