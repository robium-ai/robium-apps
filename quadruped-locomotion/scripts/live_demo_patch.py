#!/usr/bin/env python3
"""Patch Isaac Lab's compatibility play script into the Go2 live controller."""

import argparse
import os
from pathlib import Path

root = Path(os.environ.get("ISAACLAB_ROOT", "/workspace/IsaacLab"))
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--play",
    type=Path,
    default=root / "scripts/reinforcement_learning/rsl_rl/play.py",
)
parser.add_argument(
    "--output",
    type=Path,
    default=root / "scripts/reinforcement_learning/rsl_rl/live_demo.py",
)
args = parser.parse_args()
src = args.play.read_text()

src = src.replace('render_mode="rgb_array" if args_cli.video else None', 'render_mode="rgb_array"')

anchor = "env_cfg.scene.num_envs = args_cli.num_envs if args_cli.num_envs is not None else env_cfg.scene.num_envs"
tweak = anchor + """
        try:
            _bv = env_cfg.commands.base_velocity
            _bv.heading_command = False
            _bv.resampling_time_range = (1.0e6, 1.0e6)
            _bv.rel_standing_envs = 0.0
            print("LIVE: base_velocity command made controllable", flush=True)
        except Exception as _e:
            print("LIVE: cmd cfg tweak skipped:", _e, flush=True)"""
assert anchor in src, "R2 anchor missing"
src = src.replace(anchor, tweak)

PAGE_HTML = """<!doctype html><html><head><meta charset=utf-8><title>Go2 Live Control</title>
<meta name=viewport content=\"width=device-width,initial-scale=1\">
<style>
*{box-sizing:border-box}html,body{height:100%}body{background:#090c12;color:#f7f8fa;font-family:system-ui,-apple-system,sans-serif;margin:0;overflow:hidden}
.app{display:grid;grid-template-columns:300px minmax(0,1fr);height:100%;min-height:0}
.controls{display:flex;min-height:0;flex-direction:column;gap:16px;overflow:auto;border-right:1px solid #2a3140;background:#0d1119;padding:22px}
h1{margin:0;font-size:22px;line-height:1.1}p{margin:5px 0 0;color:#aab1bf;font-size:12px;line-height:1.5}
.field{display:grid;gap:7px}.label{display:flex;align-items:center;justify-content:space-between;gap:12px;color:#f7f8fa;font-size:13px;font-weight:650}.value{color:#8db4ff;font:12px ui-monospace,monospace}
select{width:100%;border:1px solid #343c4e;border-radius:6px;background:#151a24;color:#f7f8fa;padding:10px;font-size:13px}
input[type=range]{width:100%;margin:0;accent-color:#4c8dff}
.presets{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}
button{min-height:38px;border:1px solid #343c4e;border-radius:6px;background:#151a24;color:#e8edf7;padding:8px 10px;font-size:12px;font-weight:650;cursor:pointer}
button:hover{border-color:#6f9bff}.stop{border-color:#2f65d8;background:#2356bd}.reset{grid-column:1/-1;background:transparent}
.keys{display:grid;grid-template-columns:repeat(3,32px);justify-content:center;gap:5px;margin-top:auto}.key{display:grid;height:30px;place-items:center;border:1px solid #343c4e;border-radius:5px;background:#151a24;color:#aab1bf;font:11px ui-monospace,monospace}.key.blank{visibility:hidden}
.hint{text-align:center;color:#737c8e;font-size:11px}.camera{display:flex;min-width:0;min-height:0;align-items:center;justify-content:center;background:#05070b;padding:14px}
#v{display:block;width:100%;height:100%;min-height:0;background:#000;object-fit:contain}
@media(max-width:700px){body{overflow:auto}.app{grid-template-columns:1fr;height:auto;min-height:100%}.controls{overflow:visible;border-right:0;border-bottom:1px solid #2a3140;padding:16px}.camera{min-height:54vh}.keys,.hint{display:none}}
</style></head>
<body><main class=app>
<aside class=controls>
  <div><h1>Go2 control</h1><p>Drive the robot, then change checkpoints to feel how the policy improves.</p></div>
  <label class=field><span class=label><span>Checkpoint</span><span id=curckpt class=value>loading…</span></span><select id=ckpt></select></label>
  <label class=field><span class=label><span>Forward</span><span id=lvx class=value>0.50</span></span><input type=range id=vx min=-1.5 max=1.5 step=0.05 value=0.5></label>
  <label class=field><span class=label><span>Strafe</span><span id=lvy class=value>0.00</span></span><input type=range id=vy min=-1 max=1 step=0.05 value=0></label>
  <label class=field><span class=label><span>Turn</span><span id=lyaw class=value>0.00</span></span><input type=range id=yaw min=-1.5 max=1.5 step=0.05 value=0></label>
  <div class=presets>
    <button onclick=\"preset(0.8,0,0)\">Forward</button><button onclick=\"preset(-0.6,0,0)\">Back</button>
    <button onclick=\"preset(0,0.6,0)\">Strafe</button><button onclick=\"preset(0,0,1.0)\">Turn</button>
    <button class=stop onclick=\"preset(0,0,0)\">Stop</button><button onclick=\"resetSim()\">Reset robot</button>
  </div>
  <div class=keys><span class=key>Q</span><span class=key>W</span><span class=key>E</span><span class=key>A</span><span class=key>S</span><span class=key>D</span></div>
  <div class=hint>Hold W/A/S/D or arrow keys to move · Q/E to strafe</div>
</aside>
<section class=camera><img id=v src=\"__BASE__/stream\" alt=\"Live Isaac Sim view of the Unitree Go2\"></section>
</main>
<script>
const g=id=>document.getElementById(id);
const BASE='__BASE__';
function post(url,obj){return fetch(BASE+url,{method:'POST',body:JSON.stringify(obj)}).catch(()=>{});}
function send(){const b={vx:+g('vx').value,vy:+g('vy').value,yaw:+g('yaw').value};
 g('lvx').textContent=b.vx.toFixed(2);g('lvy').textContent=b.vy.toFixed(2);g('lyaw').textContent=b.yaw.toFixed(2);post('/cmd',b);}
['vx','vy','yaw'].forEach(id=>g(id).addEventListener('input',send));
function preset(x,y,w){g('vx').value=x;g('vy').value=y;g('yaw').value=w;send();}
function resetSim(){post('/reset',{});}
// keyboard
const keys={};
function kc(){let vx=0,vy=0,yaw=0;
 if(keys['w']||keys['arrowup'])vx+=0.8; if(keys['s']||keys['arrowdown'])vx-=0.6;
 if(keys['a']||keys['arrowleft'])yaw+=1.0; if(keys['d']||keys['arrowright'])yaw-=1.0;
 if(keys['q'])vy+=0.6; if(keys['e'])vy-=0.6;
 g('vx').value=vx;g('vy').value=vy;g('yaw').value=yaw;send();}
const KK=['w','a','s','d','q','e','arrowup','arrowdown','arrowleft','arrowright'];
window.addEventListener('keydown',e=>{const k=e.key.toLowerCase();if(KK.includes(k)){if(!keys[k]){keys[k]=1;kc();}e.preventDefault();}});
window.addEventListener('keyup',e=>{const k=e.key.toLowerCase();if(keys[k]){delete keys[k];kc();e.preventDefault();}});
// checkpoints
fetch(BASE+'/ckpts').then(r=>r.json()).then(d=>{const s=g('ckpt');
 d.ckpts.forEach(it=>{const o=document.createElement('option');o.value=it;o.textContent='iter '+it;if(it==d.current)o.selected=true;s.appendChild(o);});
 g('curckpt').textContent='iteration '+d.current;});
g('ckpt').addEventListener('change',e=>{const it=e.target.value;g('curckpt').textContent='loading '+it+'…';
 post('/load',{ckpt:it}).then(()=>{const check=setInterval(()=>fetch(BASE+'/status').then(r=>r.json()).then(d=>{if(String(d.checkpoint)===String(it)){clearInterval(check);g('curckpt').textContent='iteration '+it;}}),300);setTimeout(()=>clearInterval(check),15000);});});
send();
</script></body></html>"""

LIVE_BLOCK = '''        # ===== LIVE INTERACTIVE DEMO =====
        import threading, io, json, glob
        import re as _re
        import numpy as _np
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from PIL import Image as _Image

        CMD = {"vx": 0.5, "vy": 0.0, "yaw": 0.0}
        LATEST = {"jpg": b""}
        PENDING = {"load": None, "reset": False}
        POLICY = {"fn": policy}
        _run_dir = os.path.dirname(resume_path)
        _ckpts = sorted(int(_re.search(r"model_(\\d+)\\.pt", _f).group(1)) for _f in glob.glob(os.path.join(_run_dir, "model_*.pt")) if _re.search(r"model_(\\d+)\\.pt", _f))
        _m0 = _re.search(r"model_(\\d+)\\.pt", os.path.basename(resume_path))
        CUR = {"ckpt": int(_m0.group(1)) if _m0 else (_ckpts[-1] if _ckpts else -1)}
        _cm = env.unwrapped.command_manager
        _vterm = _cm.get_term("base_velocity")
        print("LIVE: got base_velocity term:", type(_vterm).__name__, "cmd shape", tuple(_vterm.vel_command_b.shape), "ckpts", _ckpts, flush=True)

        def _apply_cmd():
            _vterm.vel_command_b[:, 0] = CMD["vx"]
            _vterm.vel_command_b[:, 1] = CMD["vy"]
            _vterm.vel_command_b[:, 2] = CMD["yaw"]

        _capability = os.environ.get("DEMO_CAPABILITY", "").strip()
        _BASE = "/c/" + _capability if _capability else ""
        _PAGE = __PAGE_BYTES__.replace(b"__BASE__", _BASE.encode())

        class _H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass
            def _send(self, code, ctype, body):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "close")
                self.end_headers()
                try:
                    self.wfile.write(body)
                except Exception:
                    pass
            def _route(self):
                raw = self.path.split("?", 1)[0]
                if _BASE and raw != _BASE and not raw.startswith(_BASE + "/"):
                    return None
                return raw[len(_BASE):] or "/"
            def do_GET(self):
                route = self._route()
                if route is None:
                    self._send(404, "text/plain", b"not found")
                elif route.startswith("/stream"):
                    self.send_response(200)
                    self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    try:
                        while True:
                            j = LATEST["jpg"]
                            if j:
                                self.wfile.write(b"--frame\\r\\nContent-Type: image/jpeg\\r\\n\\r\\n" + j + b"\\r\\n")
                                self.wfile.flush()
                            time.sleep(0.06)
                    except Exception:
                        pass
                elif route.startswith("/frame"):
                    self._send(200, "image/jpeg", LATEST["jpg"])
                elif route.startswith("/ckpts"):
                    self._send(200, "application/json", json.dumps({"ckpts": _ckpts, "current": CUR["ckpt"]}).encode())
                elif route.startswith("/status"):
                    self._send(200, "application/json", json.dumps({"phase": "ready", "ready": True, "checkpoint": CUR["ckpt"], "checkpoints": _ckpts}).encode())
                else:
                    self._send(200, "text/html; charset=utf-8", _PAGE)
            def do_POST(self):
                route = self._route()
                if route is None:
                    self._send(404, "text/plain", b"not found")
                    return
                n = int(self.headers.get("Content-Length", 0) or 0)
                body = self.rfile.read(n)
                try:
                    d = json.loads(body)
                except Exception:
                    d = {}
                if route.startswith("/load"):
                    try:
                        PENDING["load"] = int(d.get("ckpt"))
                    except Exception:
                        pass
                elif route.startswith("/reset"):
                    PENDING["reset"] = True
                else:
                    for k in ("vx", "vy", "yaw"):
                        if k in d:
                            try:
                                CMD[k] = max(-2.0, min(2.0, float(d[k])))
                            except Exception:
                                pass
                self._send(200, "text/plain", b"ok")

        _srv = ThreadingHTTPServer(("0.0.0.0", 8888), _H)
        threading.Thread(target=_srv.serve_forever, daemon=True).start()
        print("LIVE_SERVER_UP on 8888", flush=True)

        obs = env.get_observations()
        _n = 0
        try:
            while True:
                # hot-swap checkpoint if requested (done here in the sim thread, not the HTTP thread)
                if PENDING["load"] is not None:
                    _it = PENDING["load"]
                    PENDING["load"] = None
                    try:
                        runner.load(os.path.join(_run_dir, "model_%d.pt" % _it))
                        POLICY["fn"] = runner.get_inference_policy(device=env.unwrapped.device)
                        CUR["ckpt"] = _it
                        print("LIVE: loaded checkpoint", _it, flush=True)
                    except Exception as _e:
                        print("LIVE: load failed:", _e, flush=True)
                if PENDING["reset"]:
                    PENDING["reset"] = False
                    _reset = env.reset()
                    obs = _reset[0] if isinstance(_reset, tuple) else _reset
                    print("LIVE: environment reset", flush=True)
                with torch.inference_mode():
                    _apply_cmd()
                    actions = POLICY["fn"](obs)
                    obs, _, dones, _ = env.step(actions)
                    _apply_cmd()
                    try:
                        POLICY["fn"].reset(dones)
                    except Exception:
                        pass
                _n += 1
                time.sleep(0.003)  # yield the GIL so the HTTP thread stays responsive
                if _n % 3 == 0:
                    fr = env.unwrapped.render()
                    if fr is not None:
                        im = _Image.fromarray(_np.asarray(fr, dtype=_np.uint8))
                        im = im.resize((640, 360))  # lighter frame => faster transfer through the proxy
                        b = io.BytesIO()
                        im.save(b, format="JPEG", quality=55)
                        LATEST["jpg"] = b.getvalue()
            env.close()
        except KeyboardInterrupt:
            pass'''

LIVE_BLOCK = LIVE_BLOCK.replace("__PAGE_BYTES__", repr(PAGE_HTML.encode("utf-8")))

start = src.index("        # reset environment")
end = src.index("        except KeyboardInterrupt:")
end = src.index("pass", end) + len("pass")
src = src[:start] + LIVE_BLOCK + src[end:]

args.output.write_text(src)
print("WROTE", args.output, "lines", src.count(chr(10)) + 1)
