# The demo container: the browser demo app on :8765, self-contained.
# CPU-only by design — Docker on macOS cannot see MPS; native MPS runs use
# `make demo` instead. Everything the demo needs (rung checkpoints,
# ladder.json, eval videos) is fetched at BUILD time from the public Hub
# repo — no token, no local outputs/, reproducible from a bare clone.
FROM python:3.12-slim

# ffmpeg: lerobot's video stack imports torchcodec, which needs the ffmpeg
# shared libraries present even though the demo never decodes a dataset.
# build-essential: pymunk (gym-pusht's physics) ships no linux/arm64 wheel
# and compiles from source at install time.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg build-essential \
    && rm -rf /var/lib/apt/lists/*

# SDL dummy driver: pygame without a display (belt-and-braces — rgb_array
# rendering is offscreen already).
ENV SDL_VIDEODRIVER=dummy \
    PORT=8765 \
    HF_HOME=/opt/hf

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
# CPU torch first, from the PyTorch CPU index: the default linux wheel drags
# the full CUDA dependency train (nvidia-*, triton — multi-GB) that a CPU
# container never uses. Versions match uv.lock.
RUN pip install --no-cache-dir uv \
    && uv pip install --system --index-url https://download.pytorch.org/whl/cpu \
       torch==2.11.0 torchvision==0.26.0
# -e is load-bearing: config.APP_ROOT resolves from config.py's __file__, so
# the module must live at /app/src (editable), not in site-packages — or the
# fetched outputs/ tree below would never be found.
RUN uv pip install --system -e .

# Demo artifacts (rung checkpoints, real eval numbers, gallery videos) come
# from the public Hub repo — the tree mirrors outputs/ exactly.
ARG LADDER_REPO=robium/pusht-act-ladder
RUN hf download ${LADDER_REPO} --repo-type model --local-dir outputs \
    && rm -rf /opt/hf

# Boot probe at BUILD time: loads the default rung + constructs/renders the
# env — a broken fetch fails the build, not a visitor's session.
RUN python -c "from imitation_manipulation.demo.episode_runner import EpisodeRunner; EpisodeRunner()"

# Runtime never touches the Hub.
ENV HF_HUB_OFFLINE=1

EXPOSE 8765
CMD ["python", "-m", "imitation_manipulation.demo.app"]
