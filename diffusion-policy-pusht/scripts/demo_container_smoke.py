"""Boot the baked CPU image and exercise one real hosted-demo rollout."""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request


NAME = f"diffusion-policy-pusht-smoke-{os.getpid()}"


def request(base: str, method: str, path: str, body: dict | None = None):
    req = urllib.request.Request(
        base + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"content-type": "application/json"} if body is not None else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def main() -> None:
    subprocess.run(
        [
            "docker", "run", "-d", "--rm", "--name", NAME,
            "-P", "diffusion-policy-pusht:latest",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    try:
        port_text = subprocess.check_output(
            ["docker", "port", NAME, "8765/tcp"], text=True
        ).strip()
        port = port_text.rsplit(":", 1)[-1]
        base = f"http://127.0.0.1:{port}"
        deadline = time.time() + 180
        logs = ""
        while time.time() < deadline:
            logs = subprocess.check_output(
                ["docker", "logs", NAME], text=True, stderr=subprocess.STDOUT
            )
            if "DEMO READY" in logs:
                break
            if "BOOT FAILED" in logs:
                raise RuntimeError(logs)
            time.sleep(2)
        else:
            raise TimeoutError(f"container did not become ready:\n{logs[-3000:]}")

        code, status = request(base, "GET", "/status?session=smoke")
        assert code == 200 and status["ready"] and status["fleet"]["budget"] == 2
        assert request(base, "POST", "/start?session=smoke")[1]["ok"]
        assert request(base, "GET", "/status?session=intruder")[0] == 409
        assert request(base, "POST", "/shutdown?session=intruder")[0] == 403
        with urllib.request.urlopen(base + "/ui/", timeout=30) as response:
            assert b"PushT with Diffusion Policy" in response.read()

        code, submitted = request(
            base,
            "POST",
            "/ui/gradio_api/call/run_episode",
            {"data": ["official-175k", "fast", "T", 1000]},
        )
        assert code == 200
        final = None
        with urllib.request.urlopen(
            base + "/ui/gradio_api/call/run_episode/" + submitted["event_id"],
            timeout=240,
        ) as response:
            for raw in response:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:") or line == "data: null":
                    continue
                data = json.loads(line[5:])
                if isinstance(data, list) and len(data) == 4:
                    final = data[1]
                    if any(state in final for state in ("solved", "partial progress")):
                        break
        assert final and any(state in final for state in ("solved", "partial progress"))
        print(f"CONTAINER SMOKE PASS: {final}")
    finally:
        subprocess.run(
            ["docker", "stop", NAME],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


if __name__ == "__main__":
    main()
