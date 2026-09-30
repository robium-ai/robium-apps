"""Latest-frame ACT inference and hold-to-model arbitration; no torch in the UI."""

from __future__ import annotations

import json
import logging
import math
import os
import select
import subprocess
import threading
import time
import uuid
from collections import deque
from pathlib import Path

CAMERA_FEATURE = "observation.images.stackchan"
# Capture/encoding already consumes ~210 ms before a prediction is available.
# Leave room for the next 100 ms image interval and brief frame drops; expire
# from capture time so a stalled stream still cannot extend a command forever.
PREDICTION_TTL = 0.5
DEFAULT_CHECKPOINT = Path(
    ".local/training/road-v1/cloud-train/runs/train/checkpoints/step-005000"
)


def bounded_action(values):
    if len(values) != 2 or not all(math.isfinite(float(v)) for v in values):
        raise ValueError("Policy must produce two finite normalized actions")
    return tuple(max(-1.0, min(1.0, float(v))) for v in values)


def validate_checkpoint(checkpoint, power):
    checkpoint = Path(checkpoint).resolve()
    config = json.loads((checkpoint / "config.json").read_text())
    experiment = json.loads((checkpoint / "experiment.json").read_text())
    if (power != 25 or config.get("type") != "act"
            or config.get("input_features") != {
                CAMERA_FEATURE: {"type": "VISUAL", "shape": [3, 240, 320]}}
            or config.get("output_features") != {"action": {"type": "ACTION", "shape": [2]}}
            or config.get("chunk_size") != 10 or config.get("n_action_steps") != 1
            or experiment.get("motor_power") != {"throttle": 75, "steering": 25}
            or experiment.get("informative_state") is not False):
        raise ValueError("Checkpoint must match image-only ACT, 10 FPS, and T75/S25 controls")
    tilt = experiment.get("camera_tilt_deg", 0)
    if not isinstance(tilt, (int, float)) or not math.isfinite(tilt) or not 0 <= tilt <= 85:
        raise ValueError("Checkpoint camera tilt must be between 0 and 85 degrees")
    for name in ("model.safetensors", "policy_preprocessor.json", "policy_postprocessor.json"):
        if not (checkpoint / name).is_file():
            raise ValueError(f"Checkpoint missing {name}")
    return checkpoint, experiment


class HoldToModel:
    """Holding R1 or focused Space is permission for a bounded trial; manual input always wins."""

    def __init__(self, seconds=20):
        self.seconds = seconds
        self.started = None

    def choose(self, manual, *, held, connected, available, prediction, frame, now):
        if not held or not connected:
            self.started = None
            return manual, "manual"
        if self.started is None:
            self.started = now
        if any(manual):
            return manual, "manual override"
        if now - self.started >= self.seconds:
            return (0.0, 0.0), "trial complete — release R1 / Space"
        if not available or prediction is None or frame is None:
            return (0.0, 0.0), "model waiting"
        if (prediction["stream_generation"] != frame["stream_generation"]
                or prediction["sequence"] > frame["sequence"]
                or not 0 <= now - prediction["capture_t"] < PREDICTION_TTL):
            return (0.0, 0.0), "model waiting for fresh image"
        try:
            return bounded_action(prediction["raw_action"]), "model"
        except (ValueError, TypeError, KeyError):
            return (0.0, 0.0), "model invalid prediction"


class PolicyRunner:
    """One inference in flight, reading the latest frame instead of a frame queue."""

    def __init__(self, checkpoint, current_frame, *, power=25, device="mps"):
        self.checkpoint, self.experiment = validate_checkpoint(checkpoint, power)
        self.current_frame, self.device = current_frame, device
        self.project = Path(__file__).resolve().parents[2]
        self.ready = False
        self.result = None
        self.error = None
        self.process = None
        self.stop = threading.Event()
        self.thread = None
        self.prediction_times = deque(maxlen=30)
        self.root = self.project / ".local/policy-runs" / (
            time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
        )
        self.root.mkdir(parents=True)
        self.log_lock = threading.Lock()
        self.log = (self.root / "events.jsonl").open("w")
        self.stderr = (self.root / "inference.log").open("w")
        (self.root / "session.json").write_text(json.dumps({
            "checkpoint": str(self.checkpoint), "experiment": self.experiment,
            "device": device, "motion_permission": "hold R1 or focused Space; manual input overrides",
            "maximum_prediction_capture_age_s": PREDICTION_TTL,
            "trial_recordings": ".local/policy-trials (L2/R2 only)",
        }, indent=2) + "\n")

    def record(self, event):
        with self.log_lock:
            self.log.write(json.dumps(event, allow_nan=False) + "\n")
            self.log.flush()

    def observe_event(self, event):
        if event["kind"] in ("command", "hub", "hub_heartbeat", "camera_gap", "hub_busy"):
            self.record(event)

    def read_reply(self, timeout):
        if not select.select([self.process.stdout], [], [], timeout)[0]:
            raise TimeoutError("Policy inference timed out; manual control remains available")
        line = self.process.stdout.readline(16384)
        if not line:
            raise RuntimeError("Policy process exited; see inference.log")
        reply = json.loads(line)
        if reply.get("kind") == "error":
            raise RuntimeError(reply["message"])
        return reply

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        try:
            python = self.project / "training/.venv/bin/python"
            if not python.exists():
                raise RuntimeError("Run ./app build-training before loading the policy")
            if self.stop.is_set():
                return
            self.process = subprocess.Popen(
                [str(python), "-u", str(self.project / "training/live_policy.py"),
                 "--checkpoint", str(self.checkpoint), "--device", self.device],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr, bufsize=0,
                env={**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"},
            )
            if self.stop.is_set():
                return
            reply = self.read_reply(40)
            if reply.get("kind") != "ready":
                raise RuntimeError("Invalid policy startup response")
            self.record({**reply, "t": time.monotonic()})
            self.ready = True
            logging.getLogger(__name__).info(
                "ACT checkpoint step %s ready; hold R1 or Space for model, manual input overrides", reply["step"]
            )
            previous_id = None
            while not self.stop.is_set():
                frame = self.current_frame()
                if frame is None or time.monotonic() - frame["estimated_capture_t"] >= PREDICTION_TTL:
                    self.stop.wait(.01)
                    continue
                identity = (frame["stream_generation"], frame["sequence"])
                if identity == previous_id:
                    self.stop.wait(.005)
                    continue
                if tuple(frame.get(k) for k in ("width", "height", "jpeg_quality", "target_fps")) != (320, 240, 85, 10):
                    raise RuntimeError("Live camera profile must match training: 320x240, 10 FPS, Q85")
                previous_id = identity
                header = {"bytes": len(frame["jpeg"]), "sequence": frame["sequence"],
                          "stream_generation": frame["stream_generation"],
                          "capture_t": frame["estimated_capture_t"], "receipt_t": frame["t"]}
                data = memoryview(json.dumps(header).encode() + b"\n" + frame["jpeg"])
                while data:
                    written = self.process.stdin.write(data)
                    if not written:
                        raise RuntimeError("Policy input pipe closed")
                    data = data[written:]
                reply = self.read_reply(1)
                if (reply.get("kind") != "prediction"
                        or (reply["stream_generation"], reply["sequence"]) != identity
                        or reply["capture_t"] != header["capture_t"]):
                    raise RuntimeError("Policy returned a prediction for the wrong image")
                bounded_action(reply["raw_action"])
                reply["t"] = time.monotonic()
                self.record(reply)
                self.prediction_times.append(reply["t"])
                self.result = reply
        except Exception as error:  # noqa: BLE001 - faults never terminate manual control
            if not self.stop.is_set():
                self.error = str(error) or type(error).__name__
                self.record({"kind": "policy_fault", "t": time.monotonic(), "reason": self.error})
                logging.getLogger(__name__).error("ACT: %s", self.error)
        finally:
            self.ready = False
            self.result = None
            if self.process and self.process.poll() is None:
                self.process.kill()
                self.process.wait(timeout=3)

    def hz(self):
        times = list(self.prediction_times)
        return (len(times) - 1) / (times[-1] - times[0]) if len(times) > 1 else 0

    def close(self):
        self.stop.set()
        if self.process and self.process.poll() is None:
            self.process.kill()
        if self.thread:
            self.thread.join(timeout=5)
        self.log.close()
        self.stderr.close()
