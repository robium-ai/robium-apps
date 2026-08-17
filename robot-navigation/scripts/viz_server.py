#!/usr/bin/env python3
"""Serve the bundled Lichtblick with a chosen default layout injected.

The demo scenario gets its viewer from demo_gateway.py, which also owns session
budgets, shutdown, and a WebSocket tunnel — all of which the local mapping
dashboard actively does not want. This is the plain alternative: static files,
one layout, no session logic.

Why inject at request time instead of at build time: the Dockerfile's layout
injection is a one-shot string replace that consumes
`/*LICHTBLICK_SUITE_DEFAULT_LAYOUT_PLACEHOLDER*/`, so index.html can only ever
carry one layout. It keeps the uninjected page as index.template.html, and this
server fills that placeholder per request from --layout. Serving a second
layout therefore costs one HTML file rather than a second copy of the bundle.

The layout is read on every request rather than cached, so editing
lichtblick/mapping-layout.json and reloading the tab is enough to see the
change — no rebuild, no restart. Panel arrangement is fiddly to get right and
that loop is the difference between minutes and an image rebuild each time.

Bind is 0.0.0.0 because the process is inside a container and the browser is on
the host; the port is published by compose, which is what actually scopes
reachability.
"""
import argparse
import functools
import http.server
import socketserver
from pathlib import Path
from urllib.parse import quote

TOKEN = '/*LICHTBLICK_SUITE_DEFAULT_LAYOUT_PLACEHOLDER*/'


class Handler(http.server.SimpleHTTPRequestHandler):

    def __init__(self, *args, layout_path=None, bridge_url=None, **kwargs):
        self.layout_path = layout_path
        self.bridge_url = bridge_url
        super().__init__(*args, **kwargs)

    def redirect_to_bridge(self):
        """Point Lichtblick at foxglove_bridge via its deep-link parameters.

        Injecting a layout does NOT connect a data source — without this the
        dashboard renders every panel correctly and shows "No data source",
        which looks like the layout is broken when it is fine. demo_gateway.py
        does the same 302; this is the same trick without the session logic.

        The URL is the one the BROWSER must reach, so it is a host-side address
        (localhost:8765 as published by compose), not a container-internal one.
        """
        target = f'/?ds=foxglove-websocket&ds.url={quote(self.bridge_url, safe="")}'
        self.send_response(302)
        self.send_header('Location', target)
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()

    def send_index(self):
        template = Path(self.directory) / 'index.template.html'
        if not template.exists():
            self.send_error(500, 'index.template.html missing — rebuild the image')
            return
        try:
            layout = Path(self.layout_path).read_text()
        except OSError as exc:
            self.send_error(500, f'cannot read layout {self.layout_path}: {exc}')
            return
        html = template.read_text()
        if TOKEN not in html:
            self.send_error(500, 'layout placeholder missing from template')
            return
        body = html.replace(TOKEN, layout).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        # The layout changes whenever the file does; never let a proxy or the
        # browser pin an old dashboard.
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path, _, query = self.path.partition('?')
        if path in ('/', '/index.html'):
            # 'ds=' in the query is what breaks the redirect loop: the second
            # request carries it and gets the real page.
            if 'ds=' not in query:
                self.redirect_to_bridge()
                return
            self.send_index()
            return
        super().do_GET()

    def log_message(self, fmt, *args):
        pass  # static asset noise would bury the launch output


class Server(socketserver.ThreadingTCPServer):
    # Without this a restart inside the container hits "Address already in use"
    # while the old socket sits in TIME_WAIT.
    allow_reuse_address = True
    daemon_threads = True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8080)
    ap.add_argument('--root', default='/opt/lichtblick')
    ap.add_argument('--layout', default='/opt/lichtblick/mapping-layout.json')
    ap.add_argument('--bridge-url', default='ws://localhost:8765',
                    help='foxglove_bridge URL as reached FROM THE BROWSER')
    args = ap.parse_args()

    handler = functools.partial(
        Handler, directory=args.root, layout_path=args.layout,
        bridge_url=args.bridge_url)
    with Server(('0.0.0.0', args.port), handler) as httpd:
        print(f'viz_server: {args.root} on :{args.port} '
              f'with layout {args.layout} -> {args.bridge_url}', flush=True)
        httpd.serve_forever()


if __name__ == '__main__':
    main()
