from __future__ import annotations

import argparse
import io
import json
import logging
import os
import queue
import time
from pathlib import Path

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"
import pygame

from .core import (
    INPUT_POLL_HZ,
    STEERING_GAIN,
    THROTTLE_GAIN,
    Controls,
    Episode,
    Workers,
    inspect_episode,
)
from .drive_mode import lease_alive, runtime_lock, write_status
from .inference_recording import InferenceEpisode
from .policy import DEFAULT_CHECKPOINT, HoldToModel, PolicyRunner
from .vendor.gamepad import GamepadManager


def drain(workers, episode, policy=None):
    while True:
        try:
            event = workers.events.get_nowait()
        except queue.Empty:
            return
        if episode:
            episode.add(event)
        if policy:
            policy.observe_event(event)


def probe(args, workers, controls):
    episode = Episode(args.root, "hardware probe: zero motor power", args.power, args.camera_only)
    start = time.monotonic()
    outcome = "interrupted"
    workers.start()
    try:
        while time.monotonic() - start < args.seconds:
            controls.update((0.0, 0.0), False)
            drain(workers, episode)
            if workers.error or workers.drive_error:
                raise RuntimeError(workers.error or workers.drive_error)
            time.sleep(0.02)
        if not args.camera_only and not workers.ready:
            raise RuntimeError("Hub never became ready")
        if workers.latest is None:
            raise RuntimeError(workers.camera_error or "No camera frames received")
        outcome = "diagnostic"
    finally:
        workers.close()
        drain(workers, episode)
        episode.close(outcome)
    print(json.dumps(inspect_episode(episode.path), indent=2))


def operator_input(reading, keys, *, focused, controller_connected):
    """Gamepad works in the background; keyboard input belongs to this window."""
    throttle, steer = reading.throttle, reading.steer
    source = "gamepad" if controller_connected else "keyboard"
    if focused and not (throttle or steer):
        throttle = float(keys[pygame.K_UP] or keys[pygame.K_w]) - float(
            keys[pygame.K_DOWN] or keys[pygame.K_s]
        )
        steer = float(keys[pygame.K_RIGHT] or keys[pygame.K_d]) - float(
            keys[pygame.K_LEFT] or keys[pygame.K_a]
        )
        if throttle or steer:
            source = "keyboard"
    return (throttle, steer), source


def model_input(reading, keys, *, focused, controller_connected):
    """Space belongs to the driving window; R1 can work in the background."""
    keyboard_held = bool(focused and keys[pygame.K_SPACE])
    gamepad_held = bool(controller_connected and reading.policy_held)
    return keyboard_held or gamepad_held, bool(focused or controller_connected)


def hold_recording(episode, args, workers, *, held, can_start, sampled_at):
    """One clip per trigger hold; drain with the release boundary already set."""
    if episode and not held:
        episode.end_capture(sampled_at)
        drain(workers, episode)
        path = episode.close("saved", ended_at=sampled_at)
        return None, f"Saved: {path.name}"
    if held and episode is None and can_start:
        episode_type = InferenceEpisode if getattr(args, "policy", None) else Episode
        episode = episode_type(args.root, args.task, args.power, args.camera_only, started_at=sampled_at)
        if getattr(args, "policy", None):
            episode.meta["policy_checkpoint"] = str(args.policy.resolve())
            episode.meta["model_control"] = "Hold R1 or focused Space; manual input overrides; predictions clamped"
            episode.write_meta()
        return episode, "Recording while L2 or R2 is held. Release both to save."
    return episode, None


def video_recording(episode, args, workers, *, pressed, can_start, sampled_at):
    """Toggle a camera clip with R, independent of gamepad triggers."""
    if not pressed:
        return episode, None
    starting = episode is None
    episode, message = hold_recording(
        episode, args, workers, held=starting, can_start=can_start, sampled_at=sampled_at,
    )
    if starting and episode:
        episode.meta.update(recording_control="R toggles camera recording",
                            head_control_mode="disabled", head_position_mapping="Uncontrolled",
                            capture_purpose="video-only images")
        episode.write_meta()
        message = "Recording camera images. Press R again to save."
    elif starting:
        message = "Waiting for live camera before recording. Press R when ready."
    return episode, message


def inference_recording(episode, args, workers, *, pressed, can_start, sampled_at):
    if not pressed:
        return episode, None
    starting = episode is None
    episode, message = hold_recording(episode, args, workers, held=starting,
                                      can_start=can_start, sampled_at=sampled_at)
    if starting and episode:
        message = "Recording inference video + decisions. R stops and saves; excluded from training."
    elif starting:
        message = "Waiting for live camera/LEGO. Press R when ready."
    elif message:
        message += " | Encoding video in background"
    return episode, message


def run(args, workers, controls):
    pygame.init()
    screen = pygame.display.set_mode((1000, 900 if args.policy else 860))
    pygame.display.set_caption("LEGO + Stack Chan | ACT trial" if args.policy
                               else "LEGO + Stack Chan | Driving capture")
    font = pygame.font.SysFont("Arial", 21)
    small = pygame.font.SysFont("Arial", 16)
    manager = GamepadManager()
    clock = pygame.time.Clock()
    episode = None
    message = "Connecting camera and LEGO..."
    last_sequence = -1
    surface = None
    running = True
    seen_interruptions = 0
    next_render = 0.0
    input_test = getattr(args, 'input_test_seconds', None)
    input_test_started = None
    input_test_path = None
    run_started = time.monotonic()
    policy = PolicyRunner(args.policy, lambda: workers.latest, power=args.power) if args.policy else None
    hold = HoldToModel(args.policy_hold_seconds) if policy else None
    previous_mode = None
    next_status = 0.0
    if policy:
        workers.head_target_tilt = policy.experiment.get("camera_tilt_deg", 0)
        policy.start()
    workers.start()
    try:
        while running:
            requests = []
            for event in pygame.event.get():
                manager.handle_event(event)
                if event.type == pygame.QUIT:
                    running = False
                if event.type == pygame.JOYDEVICEREMOVED:
                    controls.update((0.0, 0.0), False)
                if event.type == pygame.KEYDOWN and not getattr(event, "repeat", False):
                    requests.append(event.key)
            focus = bool(pygame.key.get_focused())
            keys = pygame.key.get_pressed()
            reading = manager.read()
            sampled_at = time.monotonic()
            if input_test and input_test_started is None and sampled_at - run_started > 25:
                raise RuntimeError('Input test could not start: need a connected gamepad and live camera')
            requested, source = operator_input(
                reading, keys, focused=focus, controller_connected=manager.active is not None,
            )
            throttle, steer = requested
            if input_test_started and sampled_at - input_test_started >= input_test:
                running = False
            if pygame.K_ESCAPE in requests or pygame.K_q in requests:
                running = False
            if not lease_alive(getattr(args, 'panel_lease', None)):
                running = False
            if not running or workers.error:
                throttle, steer = 0.0, 0.0
            if focus and running and not workers.error and not args.video_only:
                workers.adjust_tilt(5 * ((pygame.K_t in requests) - (pygame.K_g in requests)))
            frame = workers.latest
            fresh = frame and time.monotonic() - frame["t"] < 0.5
            drive_available = bool(
                not args.camera_only and workers.ready and workers.head_ready
                and fresh and running and not workers.error
            )
            model_held, model_connected = model_input(
                reading, keys, focused=focus, controller_connected=manager.active is not None,
            )
            prediction = policy.result if policy else None
            mode = "manual"
            if policy:
                (throttle, steer), mode = hold.choose(
                    (throttle, steer), held=model_held and running,
                    connected=model_connected,
                    available=drive_available and policy.ready, prediction=prediction,
                    frame=frame, now=sampled_at,
                )
                if mode == "model":
                    source = "policy"
                if mode != previous_mode:
                    policy.record({"kind": "control_mode", "t": sampled_at, "mode": mode,
                                   "manual_action": list(requested), "action": [throttle, steer]})
                    previous_mode = mode
            controls.update((throttle, steer), drive_available)
            controls.refresh_action(
                (throttle, steer), sampled_at=sampled_at,
                sample={
                    'source': source, 'controller': manager.label,
                    'controller_connected': manager.active is not None,
                    'joystick_action': [reading.throttle, reading.steer],
                    'requested_action': list(requested),
                    'head_action': [0.0, workers.head_target_tilt / 85.0],
                    'focused': focus,
                    'recording_triggers': [reading.l2, reading.r2],
                    'record_held': reading.record_held,
                    'model_held': model_held,
                    'control_mode': mode,
                    'policy_frame': ({k: prediction[k] for k in (
                        'sequence', 'stream_generation', 'capture_t')} if source == 'policy' else None),
                },
            )
            if not input_test:
                can_record = bool(fresh and running and not workers.error
                                  and (workers.ready or args.camera_only))
                if policy:
                    episode, recording_message = inference_recording(
                        episode, args, workers, pressed=focus and pygame.K_r in requests,
                        can_start=can_record, sampled_at=sampled_at,
                    )
                elif args.video_only:
                    episode, recording_message = video_recording(
                        episode, args, workers, pressed=focus and pygame.K_r in requests,
                        can_start=can_record, sampled_at=sampled_at,
                    )
                else:
                    episode, recording_message = hold_recording(
                        episode, args, workers,
                        held=reading.record_held and manager.active is not None,
                        can_start=can_record, sampled_at=sampled_at,
                    )
                if recording_message:
                    message = recording_message
            if policy and episode:
                episode.record_decision(prediction, mode=mode, selected_action=(throttle, steer),
                                        manual_action=requested, available=drive_available,
                                        held=model_held, sampled_at=sampled_at)
            drain(workers, episode, policy)
            if input_test and input_test_started is None and fresh and manager.active is not None:
                episode = Episode(args.root, 'joystick/image pairing diagnostic', args.power, True)
                input_test_started = sampled_at
                input_test_path = episode.path
                message = 'Input pairing test: robot motion disabled'
            if workers.interruptions != seen_interruptions:
                seen_interruptions = workers.interruptions
                if episode and not episode.meta["camera_only"]:
                    episode.close("interrupted")
                    episode = None
            if workers.notice:
                message = workers.notice
            if (
                (workers.ready or args.camera_only)
                and fresh
                and message == "Connecting camera and LEGO..."
            ):
                message = ("Press R to record inference video + decisions (not training data)." if policy
                           else "Press R to record camera images; press R again to save." if args.video_only
                           else "Controller drives anytime, including in background. Hold L2 or R2 to record.")
                if args.camera_only:
                    message = "Camera fixed at 0° / 0°. Hold L2 or R2 to record."
                if args.video_only:
                    message = "Camera baseline running. Hold L2 or R2 to record."
            if workers.error:
                controls.update((0.0, 0.0), False)
                if episode:
                    episode.close("interrupted")
                    episode = None
                message = "STOPPED: " + workers.error
            # SDL input stays on its owning thread; render at 30 Hz while polling
            # input up to 120 Hz. Disk writes/render work may lower actual polling.
            now = time.monotonic()
            if now < next_render:
                clock.tick(INPUT_POLL_HZ)
                continue
            next_render = now + 1 / 30
            frame_id = (frame["stream_generation"], frame["sequence"]) if frame else None
            if frame and frame_id != last_sequence:
                surface = pygame.transform.scale(
                    pygame.image.load(io.BytesIO(frame["jpeg"])), (800, 600)
                )
                last_sequence = frame_id
            screen.fill((15, 21, 29))
            if surface:
                screen.blit(surface, (100, 0))
            if not fresh:
                shade = pygame.Surface((800, 600), pygame.SRCALPHA)
                shade.fill((0, 0, 0, 150))
                screen.blit(shade, (100, 0))
                screen.blit(font.render("NO LIVE VIDEO — reconnecting", True, (255, 130, 140)), (280, 280))
            state = ("DRIVE READY — controller works in background" if drive_available
                     else "DRIVE WAITING — connections or live video unavailable")
            if args.camera_only:
                state = "CAMERA ONLY — T / G adjust tilt"
            if args.video_only:
                state = "VIDEO ONLY — LEGO and head control disabled"
            if policy and drive_available:
                state = ("MODEL DRIVING — release R1 / Space to stop" if mode == 'model'
                         else "MANUAL — hold R1 or Space for model" if mode == 'manual'
                         else mode.upper())
            color = (110, 235, 185) if drive_available else (255, 197, 95)
            screen.blit(font.render(state, True, color), (24, 605))
            label = f"{manager.label} | Power T{min(100, args.power * THROTTLE_GAIN)}/S{min(100, args.power * STEERING_GAIN)}% | throttle {throttle:+.2f}, steer {steer:+.2f}"
            if workers.head_state:
                label += f" | pan {workers.head_state['yaw_deg']:.0f}°, tilt {workers.head_state['pitch_deg']:.0f}°"
            if args.video_only:
                label = f"{manager.label} | Input {controls.input_rate():.0f}/{INPUT_POLL_HZ} Hz | Camera-only preview"
            else:
                label += f" | Tilt target {workers.head_target_tilt:.0f}° | T up / G down"
            screen.blit(small.render(label, True, (220, 230, 240)), (24, 638))
            help_text = "LEFT throttle | RIGHT steering | T/G tilt | HOLD L2/R2 record | Q quit"
            if args.camera_only:
                help_text = "T/G tilt | HOLD L2/R2 record | Release both to save | Q quit"
            if args.video_only:
                help_text = "R start / stop recording images | Q quit | Click this window for keyboard input"
            if policy:
                help_text = "Space/R1: AI drive | R: record/stop | T/G: tilt | Q: quit"
            screen.blit(
                small.render(
                    help_text,
                    True,
                    (180, 200, 215),
                ),
                (24, 667),
            )
            status = (
                f"REC {episode.frames} images | {episode.frame_actions} paired actions | {episode.commands} BLE writes"
                if episode else message
            )
            screen.blit(
                small.render(status[:115], True, (255, 130, 140) if episode else (180, 200, 215)),
                (24, 698),
            )
            stats = workers.camera_metrics.snapshot()
            quality = stats.get('jpeg_quality') or 75
            target_fps = stats.get('target_fps') or 8
            age = f"{stats['age_s'] * 1000:.0f} ms" if stats['age_s'] is not None else "unknown"
            p95 = f"{stats['gap_p95_s'] * 1000:.0f} ms" if stats['gap_p95_s'] is not None else "unknown"
            encode = f"{stats['encode_us'] / 1000:.0f}ms" if stats.get('encode_us') is not None else 'unknown'
            send = f"{stats['previous_send_us'] / 1000:.0f}ms" if stats.get('previous_send_us') is not None else 'unknown'
            link = {'ap': 'Direct Wi-Fi', 'station': 'Router Wi-Fi'}.get(stats.get('network_mode'), 'Wi-Fi')
            control_status = ("Preview only | Drive and camera movement disabled" if args.video_only
                              else "Camera independent | LEGO disabled" if args.camera_only
                              else "Camera independent | LEGO connected" if workers.ready
                              else "Camera independent | LEGO connecting")
            if not args.camera_only and workers.ready:
                drive = workers.drive_metrics.snapshot()
                reply = drive['reply_p95_ms']
                control_status = (
                    f"Direct LEGO BLE | {drive['hz']:.1f}/10 Hz sent"
                    + (f" | Write p95 {reply:.0f}ms" if reply is not None else '')
                    + f" | Heartbeat age {time.monotonic() - workers.drive_heartbeat_at:.1f}s"
                )
            telemetry = [
                f"320x240 | JPEG Q{quality} | Target {target_fps} FPS | Received {stats['received_fps']:.1f} FPS | Capture {stats['capture_fps']:.1f} FPS | Age {age}",
                f"Gaps >250ms: {stats['gaps_over_250ms']} | Gap p95: {p95} | Missing sequences: {stats['sequence_missing']} | Reconnects: {stats['reconnects']}",
                f"Encode {encode} | Send {send} | Missed slots: {stats.get('missed_slots', 'unknown')} | Stale: {stats['stale_frames']} | Sensor drops: unknown",
                link + ' | ' + (workers.camera_error or workers.drive_error or workers.head_error
                                or control_status),
            ]
            for index, text in enumerate(telemetry):
                screen.blit(small.render(text[:120], True, (180, 200, 215)), (24, 730 + index * 28))
            if policy:
                details = policy.error or "Loading ACT checkpoint..."
                if policy.ready:
                    details = f"{policy.experiment.get('environment') or 'ACT'} · step {policy.experiment['step']} | {policy.hz():.1f} Hz"
                    if prediction:
                        p = prediction['raw_action']
                        details += f" | {prediction['inference_ms']:.0f} ms | Model T{p[0]:+.2f} S{p[1]:+.2f}"
                    details += f" | Max {args.policy_hold_seconds:g}s per R1 hold"
                screen.blit(small.render(details[:122], True, (180, 220, 240)), (24, 842))
            if now >= next_status:
                next_status = now + .5
                write_status(getattr(args, 'status_file', None),
                             phase='running', lego_connected=workers.ready,
                             camera_ready=bool(fresh), head_ready=workers.head_ready,
                             controller=manager.label, controller_connected=manager.active is not None,
                             policy_ready=bool(policy and policy.ready),
                             policy_hz=policy.hz() if policy else 0,
                             policy_environment=policy.experiment.get("environment") if policy else None,
                             policy_step=policy.experiment["step"] if policy else None,
                             head_tilt_deg=(workers.head_state or {}).get("pitch_deg"),
                             mode=mode, recording=episode is not None,
                             recording_path=str(episode.path.resolve()) if episode else None,
                             camera_fps=stats['received_fps'],
                             error=workers.error or workers.drive_error or workers.head_error
                             or workers.camera_error or (policy.error if policy else None))
            pygame.display.flip()
            clock.tick(INPUT_POLL_HZ)
    finally:
        controls.update((0.0, 0.0), False)
        workers.close()
        drain(workers, episode, policy)
        if episode:
            episode.close('diagnostic' if input_test and not workers.error else 'interrupted')
        if policy:
            policy.close()
        pygame.quit()
        write_status(getattr(args, 'status_file', None), phase='stopped')
    if input_test_path:
        print(json.dumps(inspect_episode(input_test_path), indent=2))


def main():
    Path(".local").mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(".local/runtime.log"), logging.StreamHandler()],
    )
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "probe"):
        p = sub.add_parser(name)
        p.add_argument("--camera-config", type=Path, default=Path(".local/camera.json"))
        p.add_argument("--hub-name")
        p.add_argument("--power", type=int, choices=range(10, 41), default=25)
        p.add_argument("--root", type=Path, default=Path("data"))
        p.add_argument("--task", default="follow the toy road")
        p.add_argument("--camera-only", action="store_true")
        p.add_argument("--video-only", action="store_true", help="Isolate video; no LEGO or head traffic")
        p.add_argument("--seconds", type=float, default=15)
        if name == 'run':
            p.add_argument('--panel-lease', type=Path, help=argparse.SUPPRESS)
            p.add_argument('--status-file', type=Path, help=argparse.SUPPRESS)
            p.add_argument('--policy', nargs='?', const=DEFAULT_CHECKPOINT, type=Path,
                           help='Load ACT; hold R1 or Space in this window to let it drive')
            p.add_argument('--policy-hold-seconds', type=float, default=20,
                           help='Maximum model control per continuous R1 hold (default 20)')
            p.add_argument('--input-test-seconds', type=float,
                           help='Bounded camera/joystick pairing test; disables LEGO and head motion')
    p = sub.add_parser("inspect")
    p.add_argument("episode", type=Path)
    args = parser.parse_args()
    if getattr(args, 'policy', None):
        if not 0 < args.policy_hold_seconds <= 60:
            parser.error('--policy-hold-seconds must be between 0 and 60')
        if args.input_test_seconds:
            parser.error('--policy cannot be combined with --input-test-seconds')
        # Mixed policy/manual trial data never enters the expert demonstration folder.
        args.root = Path('.local/inference-recordings')
    if getattr(args, 'input_test_seconds', None) is not None:
        if args.input_test_seconds <= 0:
            parser.error('--input-test-seconds must be positive')
        args.video_only = True
    if args.command == "inspect":
        print(json.dumps(inspect_episode(args.episode), indent=2))
        return
    if args.video_only and args.root == Path("data"):
        args.root = Path(".local/video-captures")
    args.camera_only = args.camera_only or args.video_only
    config = json.loads(args.camera_config.read_text())
    controls = Controls(args.power)
    workers = Workers(
        controls, config["url"], config["key"], args.hub_name, args.camera_only, args.video_only
    )
    if args.command == 'run' and not args.camera_only:
        with runtime_lock():
            run(args, workers, controls)
    else:
        (probe if args.command == "probe" else run)(args, workers, controls)


if __name__ == "__main__":
    main()
