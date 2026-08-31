"""The webcam that watches the robot.

Capture runs on its own thread and keeps only the newest frame. A control loop
that called `read()` inline would inherit the camera's cadence and jitter; the
robot must be commanded at a steady rate whether or not a frame is ready, so the
loop asks for "the latest frame" and never waits for one.

OpenCV is imported for capture only, never for display, and the headless build
is a deliberate choice - but not because it avoids the SDL2 collision. Measured:
headless still vendors an SDL2 through its bundled ffmpeg, so importing it beside
pygame still prints macOS's duplicate Objective-C class warning, in either import
order. What headless buys is that OpenCV *cannot* open a window, so pygame stays
the only library that ever exercises the duplicated windowing classes. The
warning is noise; the crash it warns about needs two libraries fighting over a
window, and only one of these can make one.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time

import cv2
import numpy as np

# OpenCV logs backend chatter straight to stderr, and probing camera indices
# that do not exist is a normal part of discovery here, not news. The logging
# entry point has moved between OpenCV versions, so ask rather than assume.
try:
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_SILENT)
except AttributeError:  # pragma: no cover - depends on the OpenCV build
    pass


class Camera:
    """Newest-frame-wins webcam capture."""

    def __init__(
        self,
        index: int = 0,
        width: int = 640,
        height: int = 480,
        name: str | None = None,
        mapping: dict[str, int] | None = None,
    ):
        self.index = resolve_camera(index, name, mapping)
        self.width = width
        self.height = height
        self._capture: cv2.VideoCapture | None = None
        self._frame: np.ndarray | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "Camera":
        self.open()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def open(self) -> None:
        self._capture = cv2.VideoCapture(self.index)
        if not self._capture.isOpened():
            raise RuntimeError(
                f"Could not open camera {self.index}. "
                "Check macOS camera permission for your terminal, "
                "or pick another --camera index."
            )
        self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()

        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if self.latest() is not None:
                return
            time.sleep(0.02)
        raise RuntimeError(f"Camera {self.index} opened but delivered no frames.")

    def _pump(self) -> None:
        assert self._capture is not None
        while not self._stop.is_set():
            ok, frame = self._capture.read()
            if not ok:
                time.sleep(0.01)
                continue
            # Hand the rest of the app RGB; OpenCV alone speaks BGR.
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            with self._lock:
                self._frame = rgb

    def latest(self) -> np.ndarray | None:
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    @property
    def shape(self) -> tuple[int, int, int]:
        frame = self.latest()
        if frame is None:
            return (self.height, self.width, 3)
        return frame.shape  # type: ignore[return-value]

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._capture is not None:
            self._capture.release()
            self._capture = None


# Cameras whose name marks them as a phone arriving over Continuity. They are
# rarely what a robot rig wants, and they appear and vanish as the phone comes
# and goes - which is what makes a bare index untrustworthy here.
_CONTINUITY_HINTS = ("iphone", "ipad", "continuity")


def camera_names() -> list[str]:
    """Camera names in the order the capture backend indexes them.

    Asked of AVFoundation directly, because OpenCV indexes into exactly this
    list - and, more importantly, because enumerating this way opens nothing.
    Discovering cameras by opening each index in turn does find them, but
    opening a Continuity camera *starts* it: the phone wakes, shows its capture
    UI, and the user is left wondering why listing cameras hijacked their
    phone. Names are metadata and should cost nothing to read.

    macOS only; other platforms get an empty list and fall back to indices.
    """
    if sys.platform != "darwin":
        return []
    try:
        import AVFoundation
    except ImportError:  # pragma: no cover - dependency guard
        return []
    try:
        devices = AVFoundation.AVCaptureDevice.devicesWithMediaType_(
            AVFoundation.AVMediaTypeVideo
        )
        return [str(d.localizedName()) for d in devices]
    except Exception:  # pragma: no cover - defensive around a native API
        return []


def describe_cameras() -> list[tuple[int, str, bool]]:
    """(index, name, is_continuity) for every camera, without opening any."""
    return [(i, name, _is_continuity(name)) for i, name in enumerate(camera_names())]


def _is_continuity(name: str) -> bool:
    lowered = name.lower()
    return any(hint in lowered for hint in _CONTINUITY_HINTS)


def device_max_resolutions() -> list[tuple[str, int, int]]:
    """(name, max_width, max_height) per camera, read from metadata only."""
    if sys.platform != "darwin":
        return []
    try:
        import AVFoundation
    except ImportError:  # pragma: no cover - dependency guard
        return []
    try:
        devices = AVFoundation.AVCaptureDevice.devicesWithMediaType_(
            AVFoundation.AVMediaTypeVideo
        )
    except Exception:  # pragma: no cover - defensive around a native API
        return []

    out = []
    for device in devices:
        best = (0, 0)
        for fmt in device.formats():
            try:
                dims = AVFoundation.CMVideoFormatDescriptionGetDimensions(
                    fmt.formatDescription()
                )
                if dims.width * dims.height > best[0] * best[1]:
                    best = (int(dims.width), int(dims.height))
            except Exception:  # pragma: no cover
                continue
        out.append((str(device.localizedName()), best[0], best[1]))
    return out


def identify_cameras(limit: int = 6) -> dict[str, int]:
    """Map camera name -> the OpenCV index that actually opens it.

    This exists because the two orderings genuinely disagree. Measured on one
    Mac, AVFoundation lists [MacBook, I930, iPhone] while OpenCV's indices open
    [I930, iPhone, MacBook] - so choosing "the camera named I930" by looking up
    its position in the AVFoundation list opens the phone instead. Nothing in
    either API exposes the other's order, and asking AVFoundation to enumerate
    in OpenCV's order does not reproduce it.

    So the correspondence is measured: each index is opened once and asked for
    its largest frame, and that resolution identifies which device it is. This
    is the one operation here that must open every camera - which briefly wakes
    a Continuity camera - so it is a deliberate, explicit step whose result is
    cached, never something that happens on an ordinary run.
    """
    known = device_max_resolutions()
    if not known:
        return {}

    mapping: dict[str, int] = {}
    for index in range(min(limit, max(len(known), 1) + 2)):
        capture = cv2.VideoCapture(index)
        try:
            if not capture.isOpened():
                continue
            # Ask for more than any camera has; each grants its own maximum.
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, 8192)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 8192)
            ok, frame = capture.read()
            if not ok or frame is None:
                continue
            height, width = frame.shape[:2]
        finally:
            capture.release()

        for name, best_w, best_h in known:
            if (best_w, best_h) == (width, height) and name not in mapping:
                mapping[name] = index
                break
    return mapping


def resolve_camera(
    index: int,
    name: str | None = None,
    mapping: dict[str, int] | None = None,
) -> int:
    """Decide which camera index to open.

    A name wins when given, because an index is not a stable identifier on
    macOS: plugging in or unplugging a phone renumbers every camera after it,
    so a rig that recorded from index 1 yesterday can silently record from a
    different lens today. Matching on the name survives that.
    """
    names = camera_names()
    if name:
        wanted = name.lower()
        # A measured mapping is the only trustworthy way from a name to an
        # OpenCV index; position in the AVFoundation list is not that.
        for found, opencv_index in (mapping or {}).items():
            if wanted in found.lower():
                return opencv_index
        matches = [n for n in names if wanted in n.lower()]
        if not matches:
            raise RuntimeError(
                f"No camera matching {name!r}. Run './app cameras' to see them."
            )
        raise RuntimeError(
            f"Camera {matches[0]!r} is known but its OpenCV index has not been "
            "measured, and the two orderings disagree - guessing would open the "
            "wrong camera. Run './app cameras --identify' once."
        )

    # No name asked for: avoid silently choosing a phone that happens to be
    # sitting at the requested index.
    if names and 0 <= index < len(names) and _is_continuity(names[index]):
        for candidate, found in enumerate(names):
            if not _is_continuity(found):
                print(
                    f"note: camera {index} is {names[index]!r} (a Continuity "
                    f"camera); using {candidate} ({found!r}) instead."
                )
                print("      pin one with: ./app config --camera-name <name>")
                return candidate
    return index


def list_cameras(limit: int = 4) -> list[int]:
    """Usable camera indices, for `./app doctor`.

    Enumerated rather than probed wherever the platform allows it, so that
    merely asking what cameras exist never starts one.
    """
    names = camera_names()
    if names:
        return list(range(len(names)))

    # No enumeration available: fall back to probing, stopping after two
    # misses in a row, since camera indices are dense from zero.
    found: list[int] = []
    misses = 0
    for index in range(limit):
        capture = cv2.VideoCapture(index)
        try:
            if capture.isOpened() and capture.read()[0]:
                found.append(index)
                misses = 0
            else:
                misses += 1
                if misses >= 2:
                    break
        finally:
            capture.release()
    return found
