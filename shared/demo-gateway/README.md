# demo-gateway — the hosted-demo session contract (reusable reference copy)

The single-process gateway every hosted robium demo speaks. Battle-tested in
robot-navigation (Cloud Run + orchestrator) and mirrored by the FastAPI
gateways in imitation-manipulation and vla-pick-and-place. Apps **vendor**
this file (copy `demo_gateway.py` into their `scripts/`) so each app stays
self-contained and promotion-ready; this copy is the source they vendor from
and the place fixes land first.

## The contract

One port (`$PORT`, default 8765), four surfaces:

| Surface | Behavior |
| --- | --- |
| WebSocket upgrade, any path | Raw byte tunnel to the Foxglove bridge at `127.0.0.1:$BRIDGE_PORT`. The first live tunnel **claims** the instance for `?session=UUID`; a second concurrent viewer gets **503** (the platform routes their retry to a fresh instance). With no live tunnel, a new session may take over the claim (page-reload semantics). |
| `POST /start?session=` | Explicit claim before any viewer connects. 503 only when another session holds a live tunnel. |
| `GET /status?session=` | 200 JSON: `{claimed, ready, rtf, nodes, uptime_s, remaining_s, fleet: {running, budget}, log: [...]}` read from `$STATUS_PATH` (written by the app's init node every ~2 s). **409** for a foreign session on a claimed instance. |
| `POST /shutdown?session=` | 200 `{bye}` then SIGINT to `$SHUTDOWN_PID` (default PID 1, the launch process — SIGTERM to PID 1 is ignored by the kernel when unhandled). **403** on session mismatch. |
| `GET /` (no `ds` param, not an upgrade) | **302** to the bundled viewer with `?ds=foxglove-websocket&ds.url=ws(s)://<this host>/…` — ws locally, wss behind a TLS proxy (`X-Forwarded-Proto`). |
| any other `GET` | Static file from `$STATIC_ROOT` (the baked-in Lichtblick web build): traversal-jailed, directories resolve to index.html, **no SPA fallback** (so removed surfaces 404), unknown paths 404. |
| `WS /logs` | Read-only stream of new `$STATUS_PATH` log lines as text frames. |

Gotchas the code already encodes — do not relearn them:

- **WebSocket upgrades ARE plain GETs**: any special-casing of `GET /` must
  exclude `Upgrade: websocket` or it hijacks the tunnel handshake.
- `Connection: close` on every HTTP response is load-bearing behind proxy
  edges that pool keep-alive.
- Exact-origin CORS with credentials (`ACAO: *` is invalid with credentials);
  `localhost:*` origins are allowed for frontend dev.

## Configuration (all env, no flags)

| Var | Default | Meaning |
| --- | --- | --- |
| `PORT` | `8765` | listen port (the platform's `$PORT`) |
| `BRIDGE_PORT` | `8766` | in-container Foxglove bridge to tunnel to |
| `STATIC_ROOT` | `/opt/lichtblick` | bundled viewer build to serve |
| `STATUS_PATH` | `/tmp/demo_status.json` | status file written by the app |
| `SESSION_SECONDS` | `1800` | session budget surfaced in /status |
| `FLEET_BUDGET` | `5` | fleet size surfaced in /status |
| `ALLOWED_ORIGINS` | robium.ai, robium.org | comma-separated exact CORS origins |
| `SHUTDOWN_PID` | `1` | pid that receives SIGINT on /shutdown |

## Testing

`python3 test_gateway.py` — stdlib-only, no ROS, no Docker: boots the gateway
against a temp static dir and a fake bridge, then asserts the redirect,
static serving + 404s, claim/409/403 guards, and shutdown signal. CI runs it
on every push (see .github/workflows/validate.yml).

## Vendoring status

- robot-navigation: vendors the pre-extraction copy (identical behavior;
  env parameterization only here). Re-vendor on its next touch.
- imitation-manipulation / vla-pick-and-place: FastAPI implementations of
  this contract; candidates to re-vendor when next touched.
