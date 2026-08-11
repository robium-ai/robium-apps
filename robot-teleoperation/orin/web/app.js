import { FoxgloveClient } from './foxglove-ws.js';
import { Teleop, LIN, ANG } from './teleop.js';

const cfg = Object.assign(
  { ROBOT_HOST: '192.0.2.10', ROBOT_WS_PORT: '8765', ROBOT_WS_URL: '', WEBCAM_STREAM_URL: '' },
  window.ENV || {}
);
const host = cfg.ROBOT_HOST;
const port = cfg.ROBOT_WS_PORT;

// Resolve the bridge WebSocket URL. ROBOT_WS_URL wins: a full ws(s):// URL is used as-is;
// a leading-slash path (e.g. "/ws") is same-origin (wss on an https page — the relay case).
// Empty falls back to ws://<host>:<port> (direct/LAN case).
function resolveWsUrl() {
  const v = (cfg.ROBOT_WS_URL || '').trim();
  if (/^wss?:\/\//.test(v)) return v;
  if (v.startsWith('/')) {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${proto}//${location.host}${v}`;
  }
  return `ws://${host}:${port}`;
}

// Webcam (hide the panel if no stream configured).
const cam = document.getElementById('webcam');
if (cfg.WEBCAM_STREAM_URL) cam.src = cfg.WEBCAM_STREAM_URL;
else cam.closest('.panel').style.display = 'none';

// Connection + status dot.
const dot = document.getElementById('status');
const client = new FoxgloveClient(resolveWsUrl(), (s) => { dot.dataset.state = s; dot.title = s; });
client.connect();

// Teleop: hold-to-drive directional buttons + keyboard.
const teleop = new Teleop(client);
teleop.bindKeyboard();
teleop.bindButton(document.getElementById('fwd'), LIN, 0);
teleop.bindButton(document.getElementById('back'), -LIN, 0);
teleop.bindButton(document.getElementById('left'), 0, ANG);
teleop.bindButton(document.getElementById('right'), 0, -ANG);

// Dock / undock.
document.getElementById('dock').addEventListener('click', () => client.dock());
document.getElementById('undock').addEventListener('click', () => client.undock());
