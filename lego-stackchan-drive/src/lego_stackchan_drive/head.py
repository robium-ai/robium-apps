"""Independent authenticated Wi-Fi head control alongside the camera stream."""

import http.client
import json
from urllib.parse import urlsplit


class HeadClient:
    def __init__(self, camera_url, key):
        # Servo motion expires independently on the device after 300 ms. A
        # delayed HTTP reply need not destroy the session or extend that motion.
        self.connection = http.client.HTTPConnection(urlsplit(camera_url).hostname, 81, timeout=1.5)
        self.key = key
        self.verified = False

    def send(self, pan, tilt):
        if not self.verified:
            self.hold()  # Never send position input to old velocity firmware.
        return self._request(pan, tilt, "absolute")

    def release(self):
        """Latch manual posing until explicit resume, including after reboot."""
        return self._request(0, 0, "release")

    def resume(self):
        """Restore powered hold at the manually selected pose."""
        return self._request(0, 0, "resume")

    def hold(self):
        return self._request(0, 0, "hold")

    def _request(self, pan, tilt, mode):
        body = json.dumps({"pan": float(pan), "tilt": float(tilt), "mode": mode})
        self.connection.request(
            "POST",
            "/head",
            body,
            {"X-Stream-Key": self.key, "Content-Type": "application/json"},
        )
        response = self.connection.getresponse()
        data = response.read(4096)
        if response.status != 200:
            raise RuntimeError(f"Head controller rejected command: HTTP {response.status}")
        state = json.loads(data)
        if state.get("control_mode") != "absolute":
            raise RuntimeError("Camera firmware needs the absolute-control update")
        self.verified = True
        return state

    def close(self):
        self.connection.close()
