#!/usr/bin/env python3
"""Serve bundled Lichtblick with this app's layout and bridge deep link."""

import argparse
import functools
import http.server
import json
import socketserver
from pathlib import Path
from urllib import error, request
from urllib.parse import quote


TOKEN = "/*LICHTBLICK_SUITE_DEFAULT_LAYOUT_PLACEHOLDER*/"


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(
        self, *args, layout_path=None, bridge_url=None, agent_url=None, **kwargs
    ):
        self.layout_path = layout_path
        self.bridge_url = bridge_url
        self.agent_url = agent_url.rstrip("/")
        super().__init__(*args, **kwargs)

    def _proxy(self, target_path, body=None, accept="application/json"):
        headers = {"Accept": accept}
        if body is not None:
            headers["Content-Type"] = "application/json"
        proxy_request = request.Request(
            self.agent_url + target_path,
            data=body,
            headers=headers,
            method="POST" if body is not None else "GET",
        )
        try:
            with request.urlopen(proxy_request, timeout=250) as response:
                status = response.status
                payload = response.read()
                content_type = response.headers.get("Content-Type", accept)
        except error.HTTPError as exc:
            status = exc.code
            payload = exc.read()
            content_type = exc.headers.get("Content-Type", "application/json")
        except (error.URLError, TimeoutError) as exc:
            status = 502
            payload = json.dumps(
                {"status": "unavailable", "reason": f"mission service: {exc}"}
            ).encode()
            content_type = "application/json"
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        path, _, query = self.path.partition("?")
        if path == "/api/health":
            self._proxy("/v1/health")
            return
        if path == "/api/camera":
            self._proxy("/v1/camera", accept="image/jpeg")
            return
        if path in ("/", "/index.html"):
            if "ds=" not in query:
                target = (
                    "/?ds=foxglove-websocket&ds.url="
                    + quote(self.bridge_url, safe="")
                )
                self.send_response(302)
                self.send_header("Location", target)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            template = Path(self.directory) / "index.template.html"
            layout = Path(self.layout_path).read_text(encoding="utf-8")
            html = template.read_text(encoding="utf-8")
            if TOKEN not in html:
                self.send_error(500, "Lichtblick layout token is missing")
                return
            body = html.replace(TOKEN, layout).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def do_POST(self):
        routes = {
            "/api/missions": "/v1/missions",
            "/api/stop": "/v1/stop",
        }
        target = routes.get(self.path)
        if target is None:
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(400, "invalid Content-Length")
            return
        if length < 0 or length > 16 * 1024:
            self.send_error(413, "request body is too large")
            return
        self._proxy(target, self.rfile.read(length))

    def log_message(self, _format, *_args):
        pass


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--root", default="/opt/lichtblick")
    parser.add_argument("--layout", default="/opt/lichtblick/layout.json")
    parser.add_argument("--bridge-url", default="ws://127.0.0.1:8765")
    parser.add_argument("--agent-url", default="http://agent:8090")
    args = parser.parse_args()
    handler = functools.partial(
        Handler,
        directory=args.root,
        layout_path=args.layout,
        bridge_url=args.bridge_url,
        agent_url=args.agent_url,
    )
    with Server(("0.0.0.0", args.port), handler) as server:
        print(f"Lichtblick console: http://127.0.0.1:{args.port}", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
