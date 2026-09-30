"""Read each distinct MJPEG frame, retaining the device's capture clock."""

import time
import urllib.request


def frames(url, key):
    request = urllib.request.Request(url, headers={"X-Stream-Key": key})
    with urllib.request.urlopen(request, timeout=2) as response:
        while True:
            headers = {}
            while True:
                line = response.readline(1024)
                if not line:
                    raise RuntimeError("Camera stream ended")
                if line.lower().startswith(b"content-length:"):
                    headers["content-length"] = line.split(b":", 1)[1].strip().decode()
                elif b":" in line:
                    name, value = line.split(b":", 1)
                    headers[name.decode().lower()] = value.strip().decode()
                elif line in (b"\r\n", b"\n") and "content-length" in headers:
                    break
            length = int(headers["content-length"])
            if not 4 <= length <= 512000:
                raise RuntimeError("Invalid camera frame length")
            jpeg = response.read(length)
            received = time.monotonic()
            if len(jpeg) != length or jpeg[:2] != b"\xff\xd8" or jpeg[-2:] != b"\xff\xd9":
                raise RuntimeError("Incomplete camera frame")
            sensor_us, sent_us = int(headers["x-sensor-us"]), int(headers["x-sent-us"])
            if not 0 <= sensor_us <= sent_us:
                raise RuntimeError("Camera supplied invalid timestamps")
            telemetry = {}
            for name in ("boot_id", "width", "height", "jpeg_quality", "target_fps", "encode_us",
                         "capture_wait_us", "previous_send_us", "missed_slots", "rssi_dbm",
                         "wifi_disconnects", "last_wifi_reason", "tcp_no_delay"):
                header = "x-" + name.replace("_", "-")
                if header in headers:
                    telemetry[name] = int(headers[header])
            for name in ("firmware", "network_mode"):
                if "x-" + name.replace("_", "-") in headers:
                    telemetry[name] = headers["x-" + name.replace("_", "-")]
            yield {
                **telemetry,
                "kind": "frame",
                "t": received,
                "sequence": int(headers["x-sequence"]),
                "sensor_us": sensor_us,
                "device_sent_us": sent_us,
                "jpeg": jpeg,
            }
