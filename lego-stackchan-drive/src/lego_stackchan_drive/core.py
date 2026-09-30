"""Independent camera/control workers, expiring controls, and raw episode storage."""

from __future__ import annotations

import asyncio
import http.client
import json
import logging
import queue
import threading
import time
import uuid
from collections import deque
from contextlib import suppress
from pathlib import Path

from .camera import frames
from .head import HeadClient
from .metrics import CAMERA_PROFILE, CameraMetrics, DriveMetrics, percentile, quality_report
from .vendor.link import HubBusyError, PybricksHubClient
from .vendor.protocol import mix

SOURCE_REVISION = "99166a1ce755edbff30d956e0e441a071ea06c9a"
INPUT_TTL = 0.25
INPUT_POLL_HZ = 120
CAMERA_TTL = 0.5
THROTTLE_SIGN = 1
THROTTLE_GAIN = 3
STEER_SIGN = -1
STEERING_GAIN = 1
BLE_SLOW_REPLY_S = 0.3
BLE_RECOVERY_S = 1.2
DRIVE_HZ = 10
HEARTBEAT_PERIOD_S = 0.25
HEARTBEAT_TIMEOUT_S = 1.0


class Controls:
    def __init__(self, power=25):
        self.lock = threading.Lock()
        self.power = power
        self.drive_available = False
        self.action = (0.0, 0.0)
        self.updated = 0.0
        self.camera_received = 0.0
        # Recording history only: motor control still reads the single latest value.
        self.input_history = deque(maxlen=INPUT_POLL_HZ * 5)

    def stop_for_link_delay(self):
        # A temporary health gate, never an operator arm/disarm latch.
        with self.lock:
            self.drive_available = False
            self.action = (0.0, 0.0)

    def update(self, action, available):
        with self.lock:
            self.action, self.drive_available, self.updated = action, available, time.monotonic()

    def refresh_action(self, action, *, sample=None, sampled_at=None):
        # Input refresh does not change worker connection availability.
        with self.lock:
            now = time.monotonic() if sampled_at is None else sampled_at
            self.action, self.updated = action, now
            if sample is not None:
                healthy = now - self.camera_received <= CAMERA_TTL
                self.input_history.append({
                    **sample, 't': now, 'drive_available': self.drive_available,
                    'effective_action': list(action) if self.drive_available and healthy else [0.0, 0.0],
                })

    def input_for_frame(self, capture_t):
        """Latest causal input sample; never attach input read after capture."""
        with self.lock:
            sample = next((row for row in reversed(self.input_history) if row['t'] <= capture_t), None)
            if sample is None:
                return None
            age = capture_t - sample['t']
            return {**sample, 'age_s': age, 'valid': age <= INPUT_TTL}

    def input_rate(self, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            rows = [row for row in self.input_history if row['t'] >= now - 2]
            return (len(rows) - 1) / (rows[-1]['t'] - rows[0]['t']) if len(rows) > 1 else 0

    def camera_tick(self, received):
        with self.lock:
            self.camera_received = received

    def command(self, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            healthy = now - self.updated <= INPUT_TTL and now - self.camera_received <= CAMERA_TTL
            action = self.action if self.drive_available and healthy else (0.0, 0.0)
            # D/B assembly: both axes reversed from the reference calibration,
            # following the operator's physical direction check.
            # Throttle and steering have independent strengths. Scale both
            # wheels together when a combined turn reaches the throttle limit.
            throttle_power = min(100, self.power * THROTTLE_GAIN)
            steering_power = min(100, self.power * STEERING_GAIN)
            wheels = mix(
                THROTTLE_SIGN * action[0],
                STEER_SIGN * action[1] * steering_power / max(1, throttle_power),
                throttle_power,
            )
            return action, wheels


class Workers:
    def __init__(self, controls, url, key, hub_name=None, camera_only=False, video_only=False):
        self.controls = controls
        self.url, self.key, self.hub_name = url, key, hub_name
        self.camera_only = camera_only or video_only
        self.video_only = video_only
        self.camera_metrics = CameraMetrics()
        self.drive_metrics = DriveMetrics()
        self.drive_heartbeat_at = 0.0
        self.command_history = deque(maxlen=128)
        self.command_history_lock = threading.Lock()
        self.drive_error = self.head_error = self.camera_error = None
        self.stop = threading.Event()
        self.events = queue.Queue(maxsize=256)
        self.latest = None
        self.error = None
        self.notice = None
        self.interruptions = 0
        self.ready = False
        self.head_ready = False
        self.head_state = None
        self.head_target_tilt = 0.0
        self.head_target_lock = threading.Lock()
        self.threads = []

    def emit(self, event):
        if event['kind'] == 'command':
            self.drive_metrics.add(event)
            with self.command_history_lock:
                self.command_history.append(dict(event))
        try:
            self.events.put_nowait(event)
        except queue.Full:
            # Preview remains independent; this session can no longer produce valid data.
            self.error = "Recorder queue overflow; restart before recording"
            self.controls.stop_for_link_delay()
            self.interruptions += 1

    def fail(self, error, source="Connection"):
        detail = str(error) or type(error).__name__
        message = f"{source}: {detail}"
        logging.getLogger(__name__).error(message)
        self.controls.update((0.0, 0.0), False)
        self.interruptions += 1
        if source == "LEGO Bluetooth":
            self.ready = False
            self.drive_error = message
        elif source == "Camera pan/tilt":
            self.head_ready = False
            self.head_error = message
        elif source == "Camera video":
            self.camera_error = message
            self.controls.camera_tick(0)
        else:
            self.error = message
        # Only explicit app shutdown sets stop. A failed actuator never kills video.

    def attach_frame_action(self, event):
        capture_t = event['estimated_capture_t']
        sample = self.controls.input_for_frame(capture_t)
        event['joystick'] = sample
        event['input_poll_hz'] = self.controls.input_rate()
        event['action_valid'] = bool(sample and sample['valid'])
        event['action'] = list(sample['effective_action']) if event['action_valid'] else None
        with self.command_history_lock:
            command = next((row for row in reversed(self.command_history)
                            if row['t'] <= capture_t), None)
        event['last_ble_command'] = (
            {**command, 'age_s': capture_t - command['t']} if command else None
        )

    def camera(self):
        failures = 0
        generation = 0
        try:
            while not self.stop.is_set():
                stream = frames(self.url, self.key)
                try:
                    offset_floor = None
                    last_sequence = -1
                    stale_since = None
                    for valid_frames, event in enumerate(stream, 1):
                        if self.stop.is_set():
                            break
                        offset = event["t"] - event["device_sent_us"] / 1e6
                        offset_floor = offset if offset_floor is None else min(offset_floor, offset)
                        if event["sequence"] <= last_sequence:
                            raise RuntimeError("Camera sequence reset")
                        event["stale"] = (
                            offset - offset_floor > 0.35
                            or event["device_sent_us"] - event["sensor_us"] > 500000
                        )
                        last_sequence = event["sequence"]
                        event["estimated_capture_t"] = event["sensor_us"] / 1e6 + offset_floor
                        event["relative_network_delay_s"] = offset - offset_floor
                        event["stream_generation"] = generation
                        self.attach_frame_action(event)
                        self.camera_metrics.add(event)
                        self.emit(event)
                        if event["stale"]:
                            self.controls.camera_tick(0)
                            self.controls.stop_for_link_delay()
                            stale_since = stale_since or event["t"]
                            self.camera_error = "Camera catching up; stale frames excluded from preview"
                            if event["t"] - stale_since > 2:
                                raise RuntimeError("Camera backlog exceeded two seconds")
                            continue
                        stale_since = None
                        self.camera_error = None
                        self.latest = event
                        self.controls.camera_tick(event["t"])
                        if valid_frames >= 10:
                            failures = 0
                    if not self.stop.is_set():
                        raise RuntimeError("Camera stream ended")
                except (OSError, http.client.HTTPException, RuntimeError) as error:
                    if self.stop.is_set():
                        break
                    self.latest = None
                    self.controls.camera_tick(0)
                    self.controls.stop_for_link_delay()
                    self.interruptions += 1
                    failures += 1
                    self.camera_error = "Camera unavailable; reconnecting automatically"
                    self.camera_metrics.reconnect()
                    self.emit(
                        {
                            "kind": "camera_gap",
                            "t": time.monotonic(),
                            "reason": str(error) or type(error).__name__,
                            "stream_generation": generation,
                        }
                    )
                    logging.getLogger(__name__).warning(
                        "Camera video interrupted; reconnecting stopped: %s", error
                    )
                finally:
                    stream.close()
                generation += 1
                self.stop.wait(min(3.0, 0.5 * max(1, failures)))
        except Exception as error:  # noqa: BLE001 - worker faults must stop motion
            self.fail(error, "Camera video")

    def check_heartbeat(self, client):
        if client.last_pong_at != self.drive_heartbeat_at:
            self.drive_heartbeat_at = client.last_pong_at
            self.emit({"kind": "hub_heartbeat", "t": self.drive_heartbeat_at})
        if time.monotonic() - client.last_pong_at >= HEARTBEAT_TIMEOUT_S:
            self.ready = False
            self.controls.stop_for_link_delay()
            raise RuntimeError("LEGO bridge heartbeat missing for 1 second; stopped")

    async def send_drive(self, client, action, wheels, *, heartbeat=False):
        """One write in flight; ACK latency is diagnostic; it does not inhibit control.

        Check heartbeat replies even while a GATT write is pending. Once it
        finishes, the next cycle reads the latest input without replaying a queue.
        """
        started = time.monotonic()
        pending = asyncio.create_task(
            client.drive(*wheels, heartbeat=True) if heartbeat else client.drive(*wheels)
        )
        try:
            while not pending.done():
                remaining = HEARTBEAT_TIMEOUT_S - (time.monotonic() - client.last_pong_at)
                await asyncio.wait({pending}, timeout=max(0, min(0.05, remaining)))
                self.check_heartbeat(client)
                if self.stop.is_set():
                    return
            await pending
            self.emit({
                "kind": "command", "t": time.monotonic(), "send_started": started,
                "action": list(action), "wheels": list(wheels),
                "delayed_ack": time.monotonic() - started > BLE_SLOW_REPLY_S,
                "hub_consumed": False, "transport_ack": True,
                "heartbeat_requested": heartbeat,
            })
        except HubBusyError:
            await self.recover_busy_hub(client, action, wheels, started)
        finally:
            if not pending.done():
                pending.cancel()
                with suppress(asyncio.CancelledError):
                    await pending
            elif not pending.cancelled():
                pending.exception()  # Retrieve faults even when heartbeat expired first.

    async def recover_busy_hub(self, client, action, wheels, started):
        self.ready = False
        self.controls.stop_for_link_delay()
        self.interruptions += 1
        self.notice = "LEGO command buffer full: recovering connection"
        self.emit({
            "kind": "hub_busy", "t": time.monotonic(), "send_started": started,
            "attempted_action": list(action), "attempted_wheels": list(wheels),
        })
        logging.getLogger(__name__).warning("LEGO command buffer full; trying zero-power recovery")
        for delay in (0.05, 0.1, 0.2):
            await asyncio.sleep(delay)
            if self.stop.is_set():
                return
            try:
                zero_started = time.monotonic()
                await asyncio.wait_for(client.drive(0, 0), BLE_SLOW_REPLY_S + BLE_RECOVERY_S)
                self.emit({
                    "kind": "command", "t": time.monotonic(), "send_started": zero_started,
                    "action": [0.0, 0.0], "wheels": [0, 0], "recovery_stop": True,
                    "hub_consumed": False,
                    "transport_ack": True,
                })
                # A GATT ACK only confirms buffering. PONG proves the bridge consumed input.
                await asyncio.wait_for(client.ping(timeout=0.5), BLE_SLOW_REPLY_S + BLE_RECOVERY_S)
            except HubBusyError:
                continue
            self.ready = not self.stop.is_set()
            self.notice = None
            logging.getLogger(__name__).warning("LEGO buffer recovered; live controller input resumes")
            return
        raise RuntimeError("Hub command buffer stayed full after three stop attempts; restart hub")

    async def drive_loop(self):
        client = PybricksHubClient(hub_name=self.hub_name, scan_timeout=5)
        try:
            hub = await client.connect()
            await client.drive(0, 0)
            await client.ping()
            self.emit({"kind": "hub", "t": time.monotonic(), "name": hub.name})
            logging.getLogger(__name__).info(
                "Direct LEGO BLE ready: %s; bridge READY and zero-power PONG confirmed", hub.name
            )
            if self.stop.is_set():
                return
            self.ready = True
            self.drive_error = None
            self.notice = None
            next_heartbeat = time.monotonic() + HEARTBEAT_PERIOD_S
            self.drive_heartbeat_at = client.last_pong_at
            while not self.stop.is_set():
                started = time.monotonic()
                self.check_heartbeat(client)
                heartbeat = started >= next_heartbeat
                if heartbeat:
                    # No catch-up heartbeat burst after a delayed write.
                    next_heartbeat = started + HEARTBEAT_PERIOD_S
                action, wheels = self.controls.command(started)
                await self.send_drive(client, action, wheels, heartbeat=heartbeat)
                await asyncio.sleep(max(0, 1 / DRIVE_HZ - (time.monotonic() - started)))
        finally:
            self.ready = False
            await client.disconnect()

    def drive(self):
        failures = 0
        while not self.stop.is_set():
            try:
                asyncio.run(self.drive_loop())
                return
            except Exception as error:  # noqa: BLE001 - retry while video remains independent
                self.fail(error, "LEGO Bluetooth")
                failures += 1
                logging.getLogger(__name__).info("LEGO reconnecting automatically")
                if self.stop.wait(min(3.0, 0.5 * failures)):
                    return

    def adjust_tilt(self, degrees):
        if self.video_only or not self.head_ready or self.stop.is_set():
            return
        with self.head_target_lock:
            self.head_target_tilt = max(0.0, min(85.0, self.head_target_tilt + degrees))

    def head(self):
        # One owner handles startup centering and later tilt requests without
        # blocking the input loop or BLE watchdog. Idle poses need no traffic.
        client = HeadClient(self.url, self.key)
        try:
            target = None
            settled = False
            startup = True
            failures = 0
            while not self.stop.is_set():
                with self.head_target_lock:
                    requested = self.head_target_tilt
                if requested != target:
                    target = requested
                    move_started = time.monotonic()
                    settled = False
                if settled:
                    self.stop.wait(.05)
                    continue
                try:
                    started = time.monotonic()
                    state = client.send(0.0, target / 85.0)
                    failures = 0
                    self.head_state = state
                    self.emit({
                        "kind": "head", "t": time.monotonic(),
                        "send_started": started, "action": [0.0, target / 85.0],
                        "startup_center": startup, "target_tilt_deg": target, **state,
                    })
                    elapsed = time.monotonic() - move_started
                    if (elapsed >= .6 and abs(state["yaw_deg"]) <= 2
                            and abs(state["pitch_deg"] - target) <= 2):
                        self.head_state = client.hold()
                        self.head_ready = True
                        self.head_error = None
                        settled = True
                        startup = False
                        logging.getLogger(__name__).info(
                            "Camera holding: yaw %.1f°, tilt %.1f° (target %.0f°)",
                            self.head_state["yaw_deg"], self.head_state["pitch_deg"], target,
                        )
                    elif elapsed > 8:
                        raise RuntimeError(f"Camera did not reach tilt target {target:.0f}°")
                    self.stop.wait(.1)
                except (OSError, http.client.HTTPException):
                    # Stop driving while servo feedback is unavailable.
                    self.head_ready = False
                    self.controls.stop_for_link_delay()
                    failures += 1
                    client.close()
                    if failures >= 3:
                        raise
                    if self.stop.wait(.2):
                        return
                    client = HeadClient(self.url, self.key)
        except Exception as error:  # noqa: BLE001 - head fault gates driving
            self.fail(error, "Camera pan/tilt")
        finally:
            with suppress(Exception):
                client.hold()
            client.close()

    def start(self):
        targets = [self.camera]
        if not self.video_only:
            targets.append(self.head)
        if not self.camera_only:
            targets.append(self.drive)
        for target in targets:
            thread = threading.Thread(target=target, daemon=True)
            self.threads.append(thread)
            thread.start()

    def close(self):
        self.controls.update((0.0, 0.0), False)
        self.stop.set()
        for thread in self.threads:
            thread.join(timeout=4)


class Episode:
    def __init__(self, root, task, power, camera_only=False, *, started_at=None):
        self.path = Path(root) / (time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
        (self.path / "frames").mkdir(parents=True)
        self.start = time.monotonic() if started_at is None else started_at
        self.frames = 0
        self.frame_actions = 0
        self.commands = 0
        self.paused = False
        self.segments = [{"segment_id": 0, "started_monotonic": self.start, "ended_monotonic": None}]
        self.log = (self.path / "events.jsonl").open("w")
        self.meta = {
            "schema_version": 7,
            "task": task,
            "started_unix": time.time(),
            "started_monotonic": self.start,
            "source_revision": SOURCE_REVISION,
            "action_names": ["throttle", "steer"],
            "head_action_names": ["pan", "tilt"],
            "head_control_mode": "keyboard_tilt",
            "head_position_mapping": "Startup yaw 0, pitch 0; T/G adjust tilt in 5 degree steps, range 0..85",
            "head_feedback": "yaw_deg/pitch_deg servo feedback, timestamped in head events",
            "drive_activation": "Automatic with healthy connections and fresh input; no arming latch",
            "background_gamepad": True,
            "recording_control": "Hold L2 or R2 to record; release both to save without a quality label",
            "recording_trigger_threshold": 0.2,
            "recording_segments": self.segments,
            "recording_pause_count": 0,
            "recording_paused": False,
            "joystick_mapping": "left Y throttle, right X steering; T/G keyboard tilt",
            "power_percent": power,
            "throttle_sign": THROTTLE_SIGN,
            "throttle_gain": THROTTLE_GAIN,
            "throttle_power_percent": min(100, power * THROTTLE_GAIN),
            "steering_gain": STEERING_GAIN,
            "steering_power_percent": min(100, power * STEERING_GAIN),
            "steer_sign": STEER_SIGN,
            "control_hz": 10,
            "heartbeat_period_s": HEARTBEAT_PERIOD_S,
            "heartbeat_timeout_s": HEARTBEAT_TIMEOUT_S,
            "hub_command_watchdog_ms": 1000,
            "hub_session_idle_ms": 5000,
            "slow_ack_policy": "Diagnostic only; does not disarm driving",
            "input_poll_target_hz": INPUT_POLL_HZ,
            "frame_action_alignment": "Latest input sample at or before estimated_capture_t; repeated values retain original sample timestamp; stale/missing samples have action=null",
            "frame_action_semantics": "Safety-gated requested action; joystick retains raw requested axes; last_ble_command is latest completed transport write at or before estimated capture, not measured motor state",
            "camera": "Stack Chan GC0308 Wi-Fi MJPEG 320x240",
            "camera_profile": dict(CAMERA_PROFILE),
            "motor_ports": {"left": "D", "right": "B"},
            "camera_only": camera_only,
            "result": "incomplete",
            "timestamp_semantics": "host receipt monotonic + device capture/send microseconds; estimated_capture_t uses minimum observed clock offset (includes unknown minimum network delay); BLE completion is not measured wheel motion",
        }
        self.write_meta()

    def write_meta(self):
        (self.path / "episode.json").write_text(json.dumps(self.meta, indent=2) + "\n")

    def write_row(self, row):
        self.log.write(json.dumps(row) + "\n")
        self.log.flush()

    def toggle_pause(self, now=None):
        now = time.monotonic() if now is None else now
        self.paused = not self.paused
        if self.paused:
            self.segments[-1]["ended_monotonic"] = now
            self.meta["recording_pause_count"] += 1
        else:
            self.segments.append({
                "segment_id": len(self.segments), "started_monotonic": now,
                "ended_monotonic": None,
            })
        self.meta["recording_paused"] = self.paused
        self.write_row({"kind": "recording_state", "t": now, "elapsed": now - self.start,
                        "paused": self.paused, "recording_segment": self.segments[-1]["segment_id"]})
        self.write_meta()
        return self.paused

    def add(self, event):
        # Filter by capture time for images and event time otherwise. Frames
        # captured during a pause stay excluded even if delivered after resume.
        event_time = event["estimated_capture_t"] if event["kind"] == "frame" else event["t"]
        segment = next((s for s in reversed(self.segments)
                        if s["started_monotonic"] <= event_time
                        and (s["ended_monotonic"] is None or event_time < s["ended_monotonic"])), None)
        if segment is None:
            return
        row = dict(event)
        row["recording_segment"] = segment["segment_id"]
        row["elapsed"] = row["t"] - self.start
        if row["kind"] == "frame":
            # Exclude a capture already in flight when the episode began.
            if row["estimated_capture_t"] < self.start:
                return
            if self.frames == 0:
                for key in ("width", "height", "jpeg_quality", "target_fps"):
                    if key in row:
                        self.meta["camera_profile"][key] = row[key]
                self.meta["camera_profile"]["max_gap_s"] = 2 / self.meta["camera_profile"]["target_fps"]
            image_path = f"frames/{self.frames:06d}.jpg"
            (self.path / image_path).write_bytes(row.pop("jpeg"))
            row["image"] = image_path
            self.frames += 1
            self.frame_actions += bool(row.get('action_valid'))
        elif row["kind"] == "command":
            self.commands += 1
        self.write_row(row)

    def end_capture(self, ended):
        if self.segments[-1]["ended_monotonic"] is None:
            self.segments[-1]["ended_monotonic"] = ended

    def close(self, result, *, ended_at=None):
        ended = time.monotonic() if ended_at is None else ended_at
        self.end_capture(ended)
        self.log.close()
        self.meta.update(
            recorded_duration_s=sum(s["ended_monotonic"] - s["started_monotonic"] for s in self.segments),
            closed_while_paused=self.paused,
            result=result,
            frames=self.frames,
            image_action_samples=self.frame_actions,
            commands=self.commands,
            ended_monotonic=ended,
        )
        self.write_meta()
        return self.path


def inspect_episode(path):
    import io

    import pygame

    path = Path(path)
    meta = json.loads((path / "episode.json").read_text())
    rows = [json.loads(line) for line in (path / "events.jsonl").read_text().splitlines()]
    frames = [row for row in rows if row["kind"] == "frame"]
    commands = [row for row in rows if row["kind"] == "command"]
    if not frames:
        raise ValueError("Episode has no camera frames")
    if not meta["camera_only"] and not commands:
        raise ValueError("Driving episode has no transmitted commands")
    for frame in frames:
        image = pygame.image.load(io.BytesIO((path / frame["image"]).read_bytes()))
        if image.get_size() != (320, 240):
            raise ValueError("Unexpected camera image size")
    return {
        "path": str(path),
        "result": meta["result"],
        "frames": len(frames),
        "commands": len(commands),
        "head_samples": sum(row["kind"] == "head" for row in rows),
        "recording_segments": len(meta.get("recording_segments", [{}])),
        "recording_pause_count": meta.get("recording_pause_count", 0),
        "recorded_duration_s": meta.get("recorded_duration_s"),
        "image_action_samples": sum(row.get('action_valid', False) for row in frames),
        "images_with_gamepad_sample": sum(
            bool(row.get('action_valid') and row.get('joystick', {}).get('source') == 'gamepad'
                 and row['joystick']['controller_connected']) for row in frames
        ),
        "input_poll_median_hz": percentile(
            [row['input_poll_hz'] for row in frames if 'input_poll_hz' in row], .5
        ),
        "image_action_max_age_ms": max(
            (row['joystick']['age_s'] * 1000 for row in frames if row.get('action_valid')),
            default=None,
        ),
        "images_without_action_sample": (
            sum(not row.get('action_valid', False) for row in frames)
            if meta['schema_version'] >= 5 else None
        ),
        **quality_report(frames, rows, meta.get("camera_profile", CAMERA_PROFILE)),
        "nonzero_commands": sum(any(row["wheels"]) for row in commands),
    }
