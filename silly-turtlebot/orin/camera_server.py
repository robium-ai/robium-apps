#!/usr/bin/env python3
"""Small DepthAI RGB camera server for the offboard OAK-D.

The server intentionally exposes a narrow HTTP surface:

* ``/health`` reports whether a fresh frame is available.
* ``/frame.jpg`` returns the latest JPEG for Gemini scene input.
* ``/stream`` returns an MJPEG stream for the browser console.
"""

from __future__ import annotations

import json
import math
import os
import socket
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import depthai as dai


FRAME_STALE_S = 3.0


class CameraState:
    def __init__(self, width: int, height: int) -> None:
        self._lock = threading.Lock()
        self._frame: bytes | None = None
        self._stream_frame: bytes | None = None
        self._captured_at = 0.0
        self._error = "camera is starting"
        self._geometry = {
            "width": width,
            "height": height,
            "horizontal_fov_deg": None,
            "vertical_fov_deg": None,
            "mount_yaw_deg": float(os.environ.get("OAKD_MOUNT_YAW_DEG", "0")),
            "mount_pitch_deg": float(os.environ.get("OAKD_MOUNT_PITCH_DEG", "0")),
        }

    def set_intrinsics(self, intrinsics) -> None:
        fx = float(intrinsics[0][0])
        fy = float(intrinsics[1][1])
        if fx <= 0 or fy <= 0:
            return
        with self._lock:
            self._geometry["horizontal_fov_deg"] = round(
                math.degrees(2.0 * math.atan(self._geometry["width"] / (2.0 * fx))),
                2,
            )
            self._geometry["vertical_fov_deg"] = round(
                math.degrees(2.0 * math.atan(self._geometry["height"] / (2.0 * fy))),
                2,
            )

    def update(self, frame: bytes, stream_frame: bytes) -> None:
        with self._lock:
            self._frame = frame
            self._stream_frame = stream_frame
            self._captured_at = time.monotonic()
            self._error = ""

    def fail(self, message: str) -> None:
        with self._lock:
            self._error = message

    def snapshot(self) -> tuple[bytes | None, float | None, str, dict]:
        with self._lock:
            frame = self._frame
            captured_at = self._captured_at
            error = self._error
            geometry = dict(self._geometry)
        age_s = None if frame is None else time.monotonic() - captured_at
        if age_s is not None and age_s > FRAME_STALE_S:
            return None, age_s, error or "camera frame is stale", geometry
        return frame, age_s, error, geometry

    def stream_snapshot(self) -> bytes | None:
        with self._lock:
            frame = self._stream_frame
            captured_at = self._captured_at
        if frame is None or time.monotonic() - captured_at > FRAME_STALE_S:
            return None
        return frame


def capture_frames(
    state: CameraState,
    width: int,
    height: int,
    fps: float,
    stream_width: int,
    stream_height: int,
    stream_quality: int,
) -> None:
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
                try:
                    calibration = device.readCalibration()
                    state.set_intrinsics(
                        calibration.getCameraIntrinsics(
                            dai.CameraBoardSocket.CAM_A, width, height
                        )
                    )
                except Exception as error:  # noqa: BLE001 - frames remain usable.
                    print(f"OAK-D calibration unavailable: {error}", flush=True)
                queue = device.getOutputQueue("rgb", maxSize=1, blocking=False)
                print(
                    f"OAK-D RGB capture ready: {width}x{height} at {fps:g} fps",
                    flush=True,
                )
                while True:
                    image = queue.get().getCvFrame()
                    ok, encoded = cv2.imencode(
                        ".jpg",
                        image,
                        [cv2.IMWRITE_JPEG_QUALITY, 82],
                    )
                    stream_image = cv2.resize(
                        image,
                        (stream_width, stream_height),
                        interpolation=cv2.INTER_AREA,
                    )
                    stream_ok, stream_encoded = cv2.imencode(
                        ".jpg",
                        stream_image,
                        [cv2.IMWRITE_JPEG_QUALITY, stream_quality],
                    )
                    if ok and stream_ok:
                        state.update(encoded.tobytes(), stream_encoded.tobytes())
        except Exception as error:  # noqa: BLE001 - camera must retry after USB resets.
            message = f"DepthAI capture failed: {error}"
            state.fail(message)
            print(message, flush=True)
            time.sleep(3.0)


def make_handler(
    state: CameraState,
    stream_fps: float = 8.0,
    stream_width: int = 320,
    stream_height: int = 180,
    stream_quality: int = 50,
):
    if not 1.0 <= stream_fps <= 12.0:
        raise ValueError("OAK-D stream FPS must be between 1 and 12")
    stream_interval_s = 1.0 / stream_fps

    class Handler(BaseHTTPRequestHandler):
        def setup(self) -> None:
            super().setup()
            # Camera clients consume a sequence of small HTTP headers followed by
            # JPEG payloads. Disabling Nagle avoids delayed-ACK stalls across the
            # robot LAN, especially for the one-frame endpoint used by Gemini.
            self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        def _write_json(self, payload: dict, status: int = HTTPStatus.OK) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            frame, age_s, error, geometry = state.snapshot()
            if self.path == "/health":
                self._write_json(
                    {
                        "status": "ok" if frame is not None else "starting",
                        "fresh": frame is not None,
                        "age_s": None if age_s is None else round(age_s, 3),
                        "error": error,
                        **geometry,
                        "stream_width": stream_width,
                        "stream_height": stream_height,
                        "stream_fps": stream_fps,
                        "stream_quality": stream_quality,
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
            if self.path == "/preview.jpg":
                preview = state.stream_snapshot()
                if preview is None:
                    self._write_json(
                        {"status": "starting", "reason": error},
                        HTTPStatus.SERVICE_UNAVAILABLE,
                    )
                    return
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(preview)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(preview)
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
                        frame = state.stream_snapshot()
                        if frame is not None:
                            part = (
                                b"--frame\r\n"
                                b"Content-Type: image/jpeg\r\n"
                                + f"Content-Length: {len(frame)}\r\n\r\n".encode()
                                + frame
                                + b"\r\n"
                            )
                            self.wfile.write(part)
                            self.wfile.flush()
                        time.sleep(stream_interval_s)
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
    width = int(os.environ.get("OAKD_WIDTH", "640"))
    height = int(os.environ.get("OAKD_HEIGHT", "360"))
    fps = float(os.environ.get("OAKD_FPS", "12"))
    stream_fps = float(os.environ.get("OAKD_STREAM_FPS", "8"))
    stream_width = int(os.environ.get("OAKD_STREAM_WIDTH", "320"))
    stream_height = int(os.environ.get("OAKD_STREAM_HEIGHT", "180"))
    stream_quality = int(os.environ.get("OAKD_STREAM_QUALITY", "50"))
    if not 1 <= stream_width <= width or not 1 <= stream_height <= height:
        raise ValueError("OAK-D stream dimensions must fit within the capture frame")
    if not 30 <= stream_quality <= 95:
        raise ValueError("OAK-D stream quality must be between 30 and 95")
    state = CameraState(width, height)
    capture = threading.Thread(
        target=capture_frames,
        args=(
            state,
            width,
            height,
            fps,
            stream_width,
            stream_height,
            stream_quality,
        ),
        daemon=True,
    )
    capture.start()
    server = ThreadingHTTPServer(
        ("0.0.0.0", 8081),
        make_handler(
            state,
            stream_fps=stream_fps,
            stream_width=stream_width,
            stream_height=stream_height,
            stream_quality=stream_quality,
        ),
    )
    print("OAK-D HTTP server: http://0.0.0.0:8081", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
