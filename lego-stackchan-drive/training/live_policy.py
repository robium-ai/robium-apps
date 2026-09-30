"""Local image-only inference subprocess. Never connects to robot hardware."""

import argparse
import contextlib
import hashlib
import io
import json
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--device", default="mps")
    args = parser.parse_args()
    output = sys.stdout
    # LeRobot prints while loading. Protocol stdout must contain only JSON.
    with contextlib.redirect_stdout(sys.stderr):
        import numpy as np
        import torch
        from PIL import Image
        from pipeline import CAMERA, device_only_batch, load_checkpoint

        policy, pre, post = load_checkpoint(args.checkpoint, args.device)

        def predict(image):
            return post(policy.predict_action_chunk(device_only_batch(pre({CAMERA: image}))))[0, 0].tolist()

        with torch.inference_mode():
            for _ in range(5):
                predict(torch.zeros((1, 3, 240, 320)))
            from pathlib import Path
            checkpoint = Path(args.checkpoint)
            step = json.loads((checkpoint / "experiment.json").read_text())["step"]
            digest = hashlib.sha256((checkpoint / "model.safetensors").read_bytes()).hexdigest()
            print(json.dumps({"kind": "ready", "step": step, "weights_sha256": digest,
                              "device": args.device}), file=output, flush=True)
            while line := sys.stdin.buffer.readline(16384):
                header = json.loads(line)
                size = header["bytes"]
                if not 4 <= size <= 512000:
                    raise ValueError("Invalid input JPEG length")
                chunks, remaining = [], size
                while remaining:
                    part = sys.stdin.buffer.read(remaining)
                    if not part:
                        raise EOFError("Truncated input JPEG")
                    chunks.append(part)
                    remaining -= len(part)
                started = time.monotonic()
                with Image.open(io.BytesIO(b"".join(chunks))) as rgb:
                    if rgb.size != (320, 240):
                        raise ValueError("Camera dimensions do not match checkpoint")
                    pixels = np.array(rgb.convert("RGB"), dtype=np.float32, copy=True) / 255
                image = torch.from_numpy(pixels).permute(2, 0, 1).contiguous().unsqueeze(0)
                action = predict(image)
                if len(action) != 2 or not np.isfinite(action).all():
                    raise ValueError("Non-finite or invalid model action")
                print(json.dumps({"kind": "prediction", "sequence": header["sequence"],
                                  "stream_generation": header["stream_generation"],
                                  "capture_t": header["capture_t"], "receipt_t": header["receipt_t"],
                                  "raw_action": action,
                                  "inference_ms": (time.monotonic() - started) * 1000}),
                      file=output, flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"kind": "error", "message": str(error)}), flush=True)
        raise
