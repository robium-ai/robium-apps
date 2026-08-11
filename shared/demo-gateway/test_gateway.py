#!/usr/bin/env python3
"""ROS-free gateway contract test. stdlib only: python3 test_gateway.py"""
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def req(url, method='GET', ok=(200,)):
    r = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(r, timeout=5) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def main():
    tmp = tempfile.mkdtemp(prefix='gwtest-')
    static = os.path.join(tmp, 'static')
    os.makedirs(static)
    with open(os.path.join(static, 'index.html'), 'w') as f:
        f.write('<html><title>viewer</title></html>')
    status_path = os.path.join(tmp, 'status.json')
    with open(status_path, 'w') as f:
        json.dump({'start': time.time(), 'ready': True, 'rtf': 1.0, 'nodes': 3,
                   'log': ['booted']}, f)

    port = free_port()
    env = dict(os.environ, PORT=str(port), STATIC_ROOT=static,
               STATUS_PATH=status_path, FLEET_BUDGET='2')

    # SHUTDOWN_PID must be the gateway's own pid (so the /shutdown test kills
    # the gateway, not this runner) — only knowable inside the child: a shell
    # execs the gateway with $$.
    gw = subprocess.Popen(
        ['/bin/sh', '-c', f'SHUTDOWN_PID=$$ exec {sys.executable} {os.path.join(HERE, "demo_gateway.py")}'],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    base = f'http://127.0.0.1:{port}'
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(base + '/status', timeout=1)
                break
            except Exception:
                time.sleep(0.1)
        else:
            raise AssertionError('gateway never came up')

        # redirect on bare /
        r = urllib.request.Request(base + '/')
        opener = urllib.request.build_opener(NoRedirect)
        try:
            resp = opener.open(r, timeout=5)
            code, loc = resp.status, ''
        except urllib.error.HTTPError as e:
            code, loc = e.code, e.headers.get('Location', '')
        assert code == 302, f'expected 302 on /, got {code}'
        assert 'ds=foxglove-websocket' in loc and 'ds.url=' in loc, loc
        print('ok: / redirects to viewer with ds params')

        # static serving + 404 + traversal
        code, body = req(base + '/?ds=foxglove-websocket')
        assert code == 200 and 'viewer' in body, (code, body)
        code, _ = req(base + '/nope.js')
        assert code == 404, code
        code, _ = req(base + '/fs/list')
        assert code == 404, code
        print('ok: static serves, unknown and removed paths 404')

        # claim + guards
        code, body = req(base + '/start?session=alpha', method='POST')
        assert code == 200 and '"ok": true' in body, (code, body)
        code, body = req(base + '/status?session=alpha')
        assert code == 200 and '"budget": 2' in body and '"ready": true' in body, (code, body)
        code, _ = req(base + '/status?session=intruder')
        assert code == 409, code
        code, _ = req(base + '/shutdown?session=intruder', method='POST')
        assert code == 403, code
        print('ok: claim honored, intruder 409/403')

        # shutdown kills the launch process (here: the gateway itself)
        code, body = req(base + '/shutdown?session=alpha', method='POST')
        assert code == 200 and 'bye' in body, (code, body)
        gw.wait(timeout=10)
        print('ok: /shutdown terminates the process')
        print('GATEWAY CONTRACT TEST PASS')
        return 0
    finally:
        if gw.poll() is None:
            gw.kill()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


if __name__ == '__main__':
    sys.exit(main())
