# Continuous Gemini Robotics Session

Status: implemented; robot deployment verification pending
Scope: `silly-turtlebot` Gemini control plane and Lichtblick mission panel
Last updated: 2026-09-14

## Objective

Make Silly TurtleBot feel continuous instead of request/response driven:

- Keep one Gemini Robotics ER 2 Streaming connection alive for the robot process.
- Let the operator start or update the active instruction from the existing text box.
- Show model text and guarded tool progress as it happens.
- Feed fresh OAK-D images to the model during an active mission.
- Preserve the current motion guard as the only path to physical actions.

The first slice should improve perceived latency and observability without
changing Nav2, docking, camera, TTS, or robot REST contracts.

## Current behavior and bottleneck

The app already uses the correct model,
`gemini-robotics-er-2-streaming-preview`, and declares physical tools with
`behavior: BLOCKING`. The inefficiency is the connection and HTTP lifecycle:

1. Lichtblick sends `POST /api/missions` and waits for one JSON response.
2. `MissionService.run()` captures one camera frame and calls `asyncio.run()`.
3. `GeminiRoboticsLiveAgent.run_once()` opens a new Live API connection.
4. It sends one image plus the instruction, executes tool calls serially, and
   waits for `turn_complete` for as long as 240 seconds.
5. The connection closes and only then does the UI receive the collected text
   and tool calls.

This means the robot can be working correctly while the panel appears idle.
It also discards conversational/session state after every button press and does
not continuously feed the scene.

The relevant current files are:

- `src/silly_turtlebot/live_agent.py`: one connection per `run_once()` call.
- `src/silly_turtlebot/mission_server.py`: blocking mission request and a new
  agent/guard per request.
- `simulation/viz_server.py`: buffers upstream responses before forwarding.
- `lichtblick-extension/src/MissionPanel.tsx`: renders only the final result.
- `src/silly_turtlebot/tools.py`: guarded, blocking Gemini tool declarations.

## Architecture decision

Use one persistent Gemini session per running robot control-plane process, not
one session per HTTP request or browser. There is one physical robot and one
authoritative action guard, so the first version supports one active mission at
a time.

```text
Lichtblick MissionPanel
  POST /api/missions ---------> 202 { mission_id }
  GET  /api/events/{id} <----- SSE text/tool/state events
             |
             v
streaming viewer proxy
             |
             v
MissionService + background asyncio runtime
  - mission state machine
  - bounded event journal
  - persistent Gemini connection
  - serialized Gemini send queue
  - receive/tool worker
  - latest-frame camera pump
             |
             v
MissionGuard -> RestRobot -> Nav2 / dock / Orin TTS
```

Do not connect the browser directly to Gemini. The API key stays in the agent
container, and every physical action continues through `MissionGuard`.

## Session lifecycle

Introduce a long-lived component such as `PersistentGeminiSession`:

1. The mission service starts one background asyncio event loop.
2. The Gemini session connects lazily on the first mission, or eagerly after
   service startup if that proves simpler.
3. One writer task serializes text, image, and tool-response writes to the
   WebSocket. No HTTP handler writes to the session directly.
4. One receive worker consumes the current model turn, emits incremental events,
   executes guarded tool calls off the event loop, and returns tool responses.
5. The connection remains open after `turn_complete` and accepts the next
   instruction on the same session.
6. Shutdown closes the session and stops the background loop cleanly.

Reconnect with bounded exponential backoff. Do not assume model context survives
a reconnect unless the installed Google Gen AI SDK exposes a verified session
resume mechanism. On a fresh connection, send the normal system instruction and
a compact snapshot of the still-relevant mission state. Never replay an
unconfirmed physical tool call.

Track processed Gemini function-call IDs for the lifetime of the connection.
If the same ID appears again, return the recorded result rather than executing
the action twice.

## Mission semantics

Keep the text box as the operator's high-level intent:

- `Run mission` starts a mission and immediately returns a mission ID.
- While a mission is active, leave the text box editable and change the action
  to `Update mission`. Submitting sends the complete current text as a new user
  instruction; do not send every keystroke.
- A new instruction updates the active objective in the same Gemini session.
- Continue to allow only one active mission because tool calls affect one real
  robot.
- `Stop robot` is always enabled, idempotent, cancels the current model turn if
  the SDK supports cancellation, clears pending mission inputs, and invokes the
  existing guarded/emergency robot stop.

Use an explicit state machine rather than a held HTTP lock:

```text
idle -> accepted -> running -> completed -> idle
                       |          |
                       v          v
                    stopping    failed
                       |          |
                       +----> idle
```

## Continuous camera and reasoning

Gemini Robotics ER 2 Streaming accepts JPEG image input at no more than 1 FPS.
Use the OAK-D camera already exposed by `RestRobot` and follow these rules:

- Run the camera pump only while a mission is active.
- Keep only the newest frame; drop stale frames instead of building a queue.
- Start at 1 frame per second, never exceed the documented limit, and make the
  interval configurable.
- Send action-triggered frames returned by `consume_camera_frames()` with higher
  priority than the next periodic frame.
- Count capture/send failures, but do not fail a navigation mission for one
  missing frame.

The human-facing camera panel has an independent, bandwidth-reduced 320x180
latest-frame path. It fetches at 1 FPS without cancelling an in-flight request,
retains the last good frame during transient failures, and retries a stalled
request after five seconds. Gemini independently retains the 640x360 scene
frame at no more than 1 FPS.

Images alone update visual context but do not trigger a reasoning turn. The
session sends a compact state-bearing heartbeat while the mission is active and
no model turn or blocking tool is unresolved. Camera frames and local
`tool.progress` events continue while a blocking ROS/Nav2 action executes, but
model-facing heartbeat text waits for the terminal function response and turn
completion. Only one heartbeat reasoning turn may be pending at any time.

Example heartbeat meaning, not required literal wording:

> [HEARTBEAT] Task active and no tool is running. Inspect the latest camera
> image, then call `ack`, one next physical action, or `complete_task` as
> appropriate.

The model-facing heartbeat is deliberately small: motion state and measured
velocity, dock state, and exceptional robot or camera alerts. It omits call IDs,
capability flags, odometry pose, normal camera freshness, camera geometry,
configured locations, and TTS internals. Stable camera geometry is supplied once
in the mission-start context. Full state remains available through
`get_robot_state` between blocking actions.

A Live API text heartbeat is a new reasoning input, not a transport keepalive.
Sending one while a blocking tool is unresolved can cancel that tool as a
barge-in. The local progress event therefore never crosses the model boundary.
If Gemini independently cancels an active tool, the service stops the robot and
fails the mission instead of allowing the model to retry an ambiguous partial
motion.

Terminal responses from motion, navigation, docking, stop, and visual-orientation
tools include a compact authoritative post-action snapshot with motion, dock,
and odometry state. This gives Gemini the state needed for its next decision
without repeating it every second. The Orin derives effective horizontal and
vertical FOV from OAK-D calibration intrinsics for the configured stream and
reports configurable mount yaw/pitch offsets.

## Blocking tool lifecycle

The receive loop remains live while a robot worker waits for a ROS action. The
original function response is sent exactly once, using the original call ID,
only after the action reaches `succeeded`, `failed`, `rejected`, or `cancelled`.
A second tool call received during that interval is rejected with active-call
metadata, logged as `tool.rejected`, and receives its own error response. A
duplicate delivery of the active call ID is logged but never executed or
answered twice.

`turn_complete` ends one Gemini reasoning turn, not the operator mission. The
mission remains active until Gemini calls `complete_task(summary)`, the operator
stops it, or a terminal failure occurs. The service sends the `complete_task`
function response before emitting `mission.completed`.

## HTTP and SSE contract

Change mission creation to acknowledge immediately:

```http
POST /v1/missions
Content-Type: application/json

{"instruction":"Find the door and move toward it in short safe steps.","camera_source":"primary"}
```

```http
HTTP/1.1 202 Accepted
Content-Type: application/json

{"status":"accepted","mission_id":"<uuid>"}
```

Stream progress from:

```http
GET /v1/events/<mission_id>
Accept: text/event-stream
```

Each domain event should have this stable envelope:

```json
{
  "seq": 17,
  "timestamp": "2026-09-09T20:00:00.123Z",
  "mission_id": "<uuid>",
  "type": "tool.finished",
  "payload": {"name": "look_around", "call_id": "call-4", "result": {"status": "succeeded"}}
}
```

Initial event types:

- `session.connecting`, `session.ready`, `session.reconnecting`
- `mission.accepted`, `mission.updated`, `mission.completed`
- `mission.stopping`, `mission.stopped`, `mission.failed`
- `input.sent`
- `model.text.delta`, `model.turn.completed`
- `tool.started`, `tool.finished`, `tool.rejected`
- `tool.response.sent`
- `camera.status` for throttled diagnostics, not one UI event per frame

Use the SSE `id` field for `seq` and the `event` field for `type`. Keep a bounded
per-mission event journal so a reconnecting `EventSource` can supply
`Last-Event-ID` and recover recent events. Always retain terminal mission and
tool-result events; text deltas and camera diagnostics may be coalesced or
dropped for a slow client.

Extend `/v1/health` with:

- Gemini session state
- active mission ID and mission state
- last event sequence
- age of the last successfully sent camera frame

The viewer proxy must stream SSE chunks and flush them as they arrive. Its
current `_proxy()` reads the complete response and therefore cannot be reused
unchanged for the event endpoint.

## Lichtblick behavior

Update `MissionPanel.tsx` to:

1. POST the instruction and receive the mission ID immediately.
2. Open an `EventSource` for that mission.
3. Render model text deltas as they arrive.
4. Add each tool call when `tool.started` arrives and update it in place on
   `tool.finished` or `tool.rejected`.
5. Show session/mission state separately from the robot health badge.
6. Keep the instruction editable and let the operator submit an update.
7. Append every event to a bounded timestamped rolling log and close the event
   stream on a terminal event or component unmount.

Do not send partial model text to TTS. Speech remains an explicit guarded
`speak` tool call and uses the existing Orin neural TTS service. The Orin adds
a configurable silent pre-roll before playback so USB-speaker wake latency
does not cut the first phonemes.

## Safety and failure rules

- `MissionGuard` remains authoritative for tool names, arguments, motion bounds,
  and docking rules.
- A Gemini timeout, unrecoverable connection failure, server shutdown, or
  operator stop must request a physical robot stop when motion may be active.
- Clear queued heartbeat and camera work when stopping.
- Never replay a tool merely because the connection was restored.
- Emit a terminal SSE event before releasing mission state when possible.
- Keep event queues bounded so a disconnected browser cannot exhaust memory.
- Reconnection must not block `/v1/stop`, `/v1/health`, dock, or undock.

## Implementation sequence

1. Refactor `live_agent.py` around a persistent session, serialized writer,
   receive/tool worker, and event callback. Preserve `run_once()` temporarily if
   the CLI still needs it.
2. Give `MissionService` a background async runtime, mission state machine, and
   bounded event journal. Make mission POST return `202` immediately.
3. Add the SSE endpoint and streaming pass-through in `viz_server.py`.
4. Update the Lichtblick panel for `EventSource`, incremental transcript/tool
   rendering, and instruction updates.
5. Add the latest-frame camera pump and idle-aware heartbeat.
6. Run the critical tests, then a supervised simulation pass and a supervised
   real-robot pass.

Likely files to change:

- `src/silly_turtlebot/live_agent.py`
- `src/silly_turtlebot/mission_server.py`
- `simulation/viz_server.py`
- `lichtblick-extension/src/MissionPanel.tsx`
- `lichtblick-extension/src/styles.css`
- `tests/test_live_agent.py`
- `tests/test_mission_server.py`
- `README.md`

## Critical tests only

Keep the automated suite focused:

1. **Persistent session:** two submitted instructions use one fake
   `live.connect()` lifetime and produce ordered incremental events.
2. **SSE contract:** mission POST returns before completion, then the stream
   emits ordered text/tool events and one terminal event; reconnect from
   `Last-Event-ID` does not duplicate earlier events.
3. **Stop and replay safety:** stopping or losing the Gemini connection invokes
   the robot stop path, clears pending inputs, and a duplicate function-call ID
   is not executed twice.

Manual acceptance in simulation and on the real robot:

- The UI acknowledges a submitted instruction within 500 ms on the local
  network, independent of Gemini's first response latency.
- Model text and tool start/finish state appear before mission completion.
- Two consecutive instructions do not create two Gemini connections.
- The OAK-D supplies fresh frames during an active mission at no more than 1 FPS.
- The operator can update the text instruction while the session remains open.
- Stop remains responsive and physically stops the robot.
- Existing Nav2, direct motion, dock/undock, camera view, and Orin speech still
  work.

## Out of scope for this slice

- Browser-to-Gemini connections or exposing the Gemini API key
- Multiple simultaneous missions, users, or robots
- Guaranteed conversation recovery across an agent-container restart
- Continuous microphone capture, wake-word detection, and full-duplex audio
- Replacing Nav2 or bypassing the guarded robot adapter
- Automatically speaking every model text delta

## References

- [Gemini Robotics ER 2 Streaming](https://ai.google.dev/gemini-api/docs/robotics-streaming)
- [Gemini Live API](https://ai.google.dev/gemini-api/docs/live-api)
- [Google Gen AI Python SDK](https://googleapis.github.io/python-genai/)
- [Prior design discussion: Google ER2 latency](https://chatgpt.com/share/6aa1c3f0-5ee0-83e9-b6ee-97d3c5cc5a39)

## Fresh-session kickoff prompt

Use this in a new Codex session:

> Work in the `robium-apps/silly-turtlebot` checkout on local `main`.
> Read `AGENTS.md` and `docs/gemini-continuous-session.md`, then implement the
> persistent Gemini Robotics ER 2 session plus SSE feedback described there.
> Keep `MissionGuard` as the only physical action path, preserve the current
> `./app run --real` workflow, and add only the three critical tests in the
> brief. Update the README for the changed operator behavior. Do not push or
> deploy. Before real-robot motion testing, use a supervised, bounded command
> and stop safely on any session failure.
