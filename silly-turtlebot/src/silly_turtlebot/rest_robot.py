"""HTTP adapter for the robot-side ROS 2 bridge.

The Gemini process does not import ROS or publish motion commands.  It calls
this small client, while the bridge translates semantic requests into Nav2
actions on the TurtleBot.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from urllib import error, parse, request


@dataclass
class RestRobot:
    base_url: str
    camera_source: str = "primary"
    camera_url: str | None = None
    tts_url: str | None = None
    timeout_s: float = 190.0
    _pending_frames: list[bytes] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError("robot URL must start with http:// or https://")
        if self.camera_source not in {"primary", "secondary"}:
            raise ValueError("camera source must be primary or secondary")
        if self.camera_url:
            self.camera_url = self.camera_url.rstrip("/")
            if not self.camera_url.startswith(("http://", "https://")):
                raise ValueError("camera URL must start with http:// or https://")
        if self.tts_url:
            self.tts_url = self.tts_url.rstrip("/")
            if not self.tts_url.startswith(("http://", "https://")):
                raise ValueError("TTS URL must start with http:// or https://")
        elif self.camera_url:
            camera = parse.urlsplit(self.camera_url)
            hostname = camera.hostname or ""
            if ":" in hostname:
                hostname = f"[{hostname}]"
            self.tts_url = parse.urlunsplit(
                (camera.scheme, f"{hostname}:8082", "", "", "")
            )

    def _json(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = request.Request(self.base_url + path, data=data, headers=headers)
        try:
            with request.urlopen(req, timeout=self.timeout_s) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            try:
                return json.loads(exc.read().decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return {"status": "failed", "reason": f"robot bridge HTTP {exc.code}"}
        except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            return {"status": "failed", "reason": f"robot bridge unavailable: {exc}"}

    def _camera(self) -> bytes | None:
        if self.camera_url:
            url = self.camera_url + "/frame.jpg"
        else:
            path = "/v1/camera/" + parse.quote(self.camera_source, safe="")
            url = self.base_url + path
        req = request.Request(url, headers={"Accept": "image/jpeg"})
        try:
            with request.urlopen(req, timeout=min(self.timeout_s, 10.0)) as response:
                frame = response.read()
                return frame if frame else None
        except (error.HTTPError, error.URLError, TimeoutError):
            return None

    def health(self) -> dict[str, Any]:
        health = self._json("/v1/health")
        if self.camera_url:
            camera_health = self._external_camera_health()
            cameras = health.setdefault("cameras", {})
            cameras[self.camera_source] = {
                "topic": self.camera_url,
                "fresh": camera_health.get("fresh") is True,
                "age_s": camera_health.get("age_s"),
                "error": camera_health.get("error", ""),
                "width": camera_health.get("width"),
                "height": camera_health.get("height"),
                "horizontal_fov_deg": camera_health.get("horizontal_fov_deg"),
                "vertical_fov_deg": camera_health.get("vertical_fov_deg"),
                "mount_yaw_deg": camera_health.get("mount_yaw_deg"),
                "mount_pitch_deg": camera_health.get("mount_pitch_deg"),
            }
        if self.tts_url:
            health["speech"] = self._external_tts_health()
        return health

    def runtime_state(self) -> dict[str, Any]:
        """Return only fast-changing state needed by heartbeats and action results."""
        health = self._json("/v1/health")
        state = {
            key: health[key]
            for key in ("status", "reason", "is_docked", "motion", "odometry")
            if health.get(key) is not None
        }
        if self.camera_url:
            camera = self._external_camera_health()
            state["cameras"] = {
                self.camera_source: {
                    key: camera[key]
                    for key in ("fresh", "age_s", "error")
                    if camera.get(key) is not None
                }
            }
        return state

    def _external_camera_health(self) -> dict[str, Any]:
        if not self.camera_url:
            return {}
        req = request.Request(
            self.camera_url + "/health", headers={"Accept": "application/json"}
        )
        try:
            with request.urlopen(req, timeout=min(self.timeout_s, 5.0)) as response:
                return json.loads(response.read().decode("utf-8"))
        except (error.HTTPError, error.URLError, TimeoutError, json.JSONDecodeError):
            return {"status": "failed", "fresh": False, "error": "unavailable"}

    def _external_tts_health(self) -> dict[str, Any]:
        if not self.tts_url:
            return {}
        req = request.Request(
            self.tts_url + "/health", headers={"Accept": "application/json"}
        )
        try:
            with request.urlopen(req, timeout=min(self.timeout_s, 5.0)) as response:
                return json.loads(response.read().decode("utf-8"))
        except (error.HTTPError, error.URLError, TimeoutError, json.JSONDecodeError):
            return {"status": "failed", "error": "unavailable"}

    def capture_camera_frame(self) -> bytes | None:
        return self._camera()

    def consume_camera_frames(self) -> list[bytes]:
        frames = self._pending_frames
        self._pending_frames = []
        return frames

    def navigate_to_location(self, location: str) -> dict[str, Any]:
        return self._json("/v1/navigate", {"location": location})

    def move_forward(self, distance_m: float) -> dict[str, Any]:
        result = self._json("/v1/move-forward", {"distance_m": distance_m})
        if result.get("status") == "succeeded":
            frame = self._camera()
            if frame:
                self._pending_frames.append(frame)
                result["camera_source"] = self.camera_source
                result["camera_frame"] = "sent_to_model"
        return result

    def move_distance(self, distance_m: float, speed_mps: float) -> dict[str, Any]:
        return self._json(
            "/v1/move-distance",
            {"distance_m": distance_m, "speed_mps": speed_mps},
        )

    def rotate_by(self, angle_deg: float) -> dict[str, Any]:
        return self._json("/v1/rotate-by", {"angle_deg": angle_deg})

    def move_for_duration(
        self, linear_mps: float, angular_rad_s: float, duration_s: float
    ) -> dict[str, Any]:
        return self._json(
            "/v1/move-for-duration",
            {
                "linear_mps": linear_mps,
                "angular_rad_s": angular_rad_s,
                "duration_s": duration_s,
            },
        )

    def look_around(self, quarter_turns: int) -> dict[str, Any]:
        result = self._json("/v1/look-around", {"quarter_turns": quarter_turns})
        if result.get("status") == "succeeded":
            frame = self._camera()
            if frame:
                self._pending_frames.append(frame)
                result["camera_source"] = self.camera_source
                result["camera_frame"] = "sent_to_model"
        return result

    def approach_object(self, object_id: str, stand_off_m: float) -> dict[str, Any]:
        return self._json(
            "/v1/approach-object",
            {"object_id": object_id, "stand_off_m": stand_off_m},
        )

    def face_nearest_person(self) -> dict[str, Any]:
        return self._json("/v1/face-nearest-person", {})

    def dock(self) -> dict[str, Any]:
        return self._json("/v1/dock", {})

    def undock(self) -> dict[str, Any]:
        return self._json("/v1/undock", {})

    def speak(self, message: str) -> dict[str, Any]:
        if self.tts_url:
            data = json.dumps({"message": message}).encode("utf-8")
            req = request.Request(
                self.tts_url + "/speak",
                data=data,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
            try:
                with request.urlopen(req, timeout=min(self.timeout_s, 45.0)) as response:
                    return json.loads(response.read().decode("utf-8"))
            except error.HTTPError as exc:
                try:
                    return json.loads(exc.read().decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    return {"status": "failed", "reason": f"TTS HTTP {exc.code}"}
            except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                return {"status": "failed", "reason": f"TTS unavailable: {exc}"}
        return self._json("/v1/speak", {"message": message})

    def stop(self, reason: str) -> dict[str, Any]:
        return self._json("/v1/stop", {"reason": reason})
