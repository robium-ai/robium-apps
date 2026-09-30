"""One-shot localhost credential entry; never prints credentials."""
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs
import json
import os
import secrets

token = secrets.token_urlsafe(24)
target = Path(__file__).parent / '.local/wifi.json'


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        if self.path != '/' + token:
            self.send_error(404)
            return
        page = '''<!doctype html><meta name="viewport" content="width=device-width"><title>Stack Chan Wi-Fi</title>
<style>body{font:18px system-ui;background:#111821;color:#eef3f8;max-width:480px;margin:70px auto;padding:24px}input,button{display:block;width:100%;box-sizing:border-box;padding:14px;margin:12px 0 26px;border-radius:8px;border:0;font:inherit}button{background:#7be1bf}p{line-height:1.5;color:#b7c4d0}</style>
<h1>Connect Stack Chan</h1><p>Enter the same Wi-Fi network used by your Mac. Stack Chan needs a 2.4 GHz network. These credentials stay on this Mac and the device.</p>
<form method="post"><label>Wi-Fi network name<input name="ssid" required maxlength="32" autocomplete="off"></label><label>Wi-Fi password<input name="password" type="password" maxlength="63" autocomplete="off"></label><button>Save locally</button></form>'''
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(page.encode())

    def do_POST(self):
        if self.path != '/' + token:
            self.send_error(403)
            return
        length = int(self.headers.get('Content-Length', '0'))
        if not 0 < length < 4096:
            self.send_error(400)
            return
        form = parse_qs(self.rfile.read(length).decode(), keep_blank_values=True)
        value = {k: form.get(k, [''])[0] for k in ('ssid', 'password')}
        if not value['ssid'] or len(value['ssid'].encode()) > 32:
            self.send_error(400)
            return
        target.parent.mkdir(exist_ok=True)
        fd = os.open(target, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w') as out:
            json.dump(value, out)
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(b'<h2>Saved locally. You can return to the task.</h2>')
        self.server.saved = True


server = HTTPServer(('127.0.0.1', 8766), Handler)
server.saved = False
print(f'http://127.0.0.1:8766/{token}', flush=True)
while not server.saved:
    server.handle_request()
server.server_close()
print('Credentials saved locally.', flush=True)
