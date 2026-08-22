# CPU demo image. The pinned official checkpoint is baked at build time so a
# visitor never waits on Hugging Face and runtime can stay fully offline.
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

ENV POLICY_DEVICE=cpu \
    HF_HOME=/opt/hf \
    PORT=8765 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app
RUN python -m pip install --no-cache-dir uv==0.11.29
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN uv sync --locked --no-dev
RUN .venv/bin/python -c "from diffusion_policy_pusht.official import build_demo_manifest; build_demo_manifest()"

FROM python:3.12-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
      libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

ENV POLICY_DEVICE=cpu \
    HF_HOME=/opt/hf \
    PORT=8765 \
    HF_HUB_OFFLINE=1

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/outputs /app/outputs
COPY src ./src

EXPOSE 8765
CMD ["/app/.venv/bin/python", "-m", "diffusion_policy_pusht.demo.gateway"]
