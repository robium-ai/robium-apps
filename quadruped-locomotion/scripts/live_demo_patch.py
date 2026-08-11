#!/usr/bin/env python3
# Patches rsl_rl/play.py into live_demo.py: live-settable velocity command, keyboard control,
# hot-swappable checkpoints, and a frame-poll server on port 8888.
PLAY = "/workspace/isaaclab/scripts/reinforcement_learning/rsl_rl/play.py"
LIVE = "/workspace/isaaclab/scripts/reinforcement_learning/rsl_rl/live_demo.py"
src = open(PLAY).read()

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
<style>body{background:#0e1013;color:#e8eaee;font-family:system-ui,-apple-system,sans-serif;margin:0;padding:18px;text-align:center}
h2{font-weight:600;margin:2px 0 10px}
#v{max-width:100%;width:760px;border-radius:12px;background:#000;aspect-ratio:16/9;object-fit:contain}
.row{display:flex;gap:18px;justify-content:center;align-items:flex-end;flex-wrap:wrap;margin:12px 0}
.sl{display:flex;flex-direction:column;align-items:center;font-size:13px;color:#a5adba}
.sl b{color:#e8eaee;font-size:14px}
input[type=range]{width:190px;margin-top:6px;accent-color:#6f9bff}
select{background:#1a2030;color:#e8eaee;border:1px solid #2a3446;border-radius:8px;padding:7px 10px;font-size:14px}
button{background:#1a2030;color:#dfe6f5;border:1px solid #2a3446;border-radius:9px;padding:9px 14px;font-size:13px;cursor:pointer;margin:3px}
button:hover{border-color:#6f9bff}
.kbd{display:inline-block;background:#1a2030;border:1px solid #2a3446;border-radius:6px;padding:2px 7px;font-size:12px;margin:0 1px}
.note{color:#6b7280;font-size:12px;margin-top:8px}
.ck{color:#6f9bff;font-size:13px}</style></head>
<body>
<h2>🐕 Go2 — live velocity control</h2>
<img id=v src=\"/stream\" alt=\"live sim\"><br>
<div class=row>
  <div class=sl><b>checkpoint</b><select id=ckpt></select></div>
  <span id=curckpt class=ck></span>
</div>
<div class=row>
  <div class=sl><b>forward vx</b><span id=lvx>0.50</span><input type=range id=vx min=-1.5 max=1.5 step=0.05 value=0.5></div>
  <div class=sl><b>strafe vy</b><span id=lvy>0.00</span><input type=range id=vy min=-1 max=1 step=0.05 value=0></div>
  <div class=sl><b>turn yaw</b><span id=lyaw>0.00</span><input type=range id=yaw min=-1.5 max=1.5 step=0.05 value=0></div>
</div>
<div class=row>
  <button onclick=\"preset(0.8,0,0)\">▶ forward</button>
  <button onclick=\"preset(0,0,0)\">■ stop</button>
  <button onclick=\"preset(0,0,1.0)\">↻ spin</button>
  <button onclick=\"preset(0,0.6,0)\">⇄ strafe</button>
  <button onclick=\"preset(-0.6,0,0)\">◀ back</button>
</div>
<div class=note>Keyboard: <span class=kbd>W</span>/<span class=kbd>↑</span> forward · <span class=kbd>S</span>/<span class=kbd>↓</span> back · <span class=kbd>A</span>/<span class=kbd>←</span> turn left · <span class=kbd>D</span>/<span class=kbd>→</span> turn right · <span class=kbd>Q</span>/<span class=kbd>E</span> strafe. Hold to move; release to stop. (Click the video once so the page has keyboard focus.)</div>
<div class=note>~10 fps via RunPod proxy · policy trained on ~[-1,1] m/s, extremes may wobble.</div>
<script>
const g=id=>document.getElementById(id);
function post(url,obj){return fetch(url,{method:'POST',body:JSON.stringify(obj)}).catch(()=>{});}
function send(){const b={vx:+g('vx').value,vy:+g('vy').value,yaw:+g('yaw').value};
 g('lvx').textContent=b.vx.toFixed(2);g('lvy').textContent=b.vy.toFixed(2);g('lyaw').textContent=b.yaw.toFixed(2);post('/cmd',b);}
['vx','vy','yaw'].forEach(id=>g(id).addEventListener('input',send));
function preset(x,y,w){g('vx').value=x;g('vy').value=y;g('yaw').value=w;send();}
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
fetch('/ckpts').then(r=>r.json()).then(d=>{const s=g('ckpt');
 d.ckpts.forEach(it=>{const o=document.createElement('option');o.value=it;o.textContent='iter '+it;if(it==d.current)o.selected=true;s.appendChild(o);});
 g('curckpt').textContent='loaded: iter '+d.current;});
g('ckpt').addEventListener('change',e=>{const it=e.target.value;g('curckpt').textContent='loading iter '+it+'…';
 post('/load',{ckpt:it}).then(()=>setTimeout(()=>g('curckpt').textContent='loaded: iter '+it,900));});
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
        PENDING = {"load": None}
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

        _PAGE = __PAGE_BYTES__

        class _H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass
            def _send(self, code, ctype, body):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except Exception:
                    pass
            def do_GET(self):
                if self.path.startswith("/stream"):
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
                elif self.path.startswith("/frame"):
                    self._send(200, "image/jpeg", LATEST["jpg"])
                elif self.path.startswith("/ckpts"):
                    self._send(200, "application/json", json.dumps({"ckpts": _ckpts, "current": CUR["ckpt"]}).encode())
                else:
                    self._send(200, "text/html; charset=utf-8", _PAGE)
            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0) or 0)
                body = self.rfile.read(n)
                try:
                    d = json.loads(body)
                except Exception:
                    d = {}
                if self.path.startswith("/load"):
                    try:
                        PENDING["load"] = int(d.get("ckpt"))
                    except Exception:
                        pass
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

open(LIVE, "w").write(src)
print("WROTE", LIVE, "lines", src.count(chr(10)) + 1)
