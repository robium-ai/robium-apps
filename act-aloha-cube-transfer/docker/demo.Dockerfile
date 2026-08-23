FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential libegl1 libgl1 libglib2.0-0 libglfw3 \
    && rm -rf /var/lib/apt/lists/*

ENV POLICY_DEVICE=cpu \
    MUJOCO_GL=egl \
    HF_HOME=/opt/hf \
    TORCH_HOME=/opt/torch \
    PORT=8765 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app
RUN python -m pip install --no-cache-dir uv==0.11.29
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN uv sync --locked --no-dev
RUN .venv/bin/python -m act_aloha_cube_transfer.run prepare-official
COPY assets/evidence.json /app/outputs/demo/evidence.json

FROM python:3.12-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
      libegl1 libgl1 libglib2.0-0 libglfw3 \
    && rm -rf /var/lib/apt/lists/*

ENV POLICY_DEVICE=cpu \
    MUJOCO_GL=egl \
    HF_HOME=/opt/hf \
    TORCH_HOME=/opt/torch \
    PORT=8765 \
    HF_HUB_OFFLINE=1

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/outputs /app/outputs
COPY --from=builder /opt/torch /opt/torch
COPY src ./src

EXPOSE 8765
CMD ["/app/.venv/bin/python", "-m", "act_aloha_cube_transfer.demo.gateway"]
