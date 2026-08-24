# syntax=docker/dockerfile:1.11

ARG PYTHON_IMAGE=python:3.10.20-slim-bookworm@sha256:019e31cc1f52e4139d338bca44f27b71339a9da261738fd80fab9cf4595152fc
ARG CUDA_BUILDER=nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04@sha256:622e78a1d02c0f90ed900e3985d6c975d8e2dc9ee5e61643aed587dcf9129f42
ARG CUDA_RUNTIME=nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04@sha256:2fcc4280646484290cc50dce5e65f388dd04352b07cbe89a635703bd1f9aedb6
ARG UV_VERSION=0.11.29
ARG LIBERO_REVISION=8f1084e3132a39270c3a13ebe37270a43ece2a01

FROM ${PYTHON_IMAGE} AS fake
ARG UV_VERSION
RUN groupadd --gid 65532 robium \
    && useradd --uid 65532 --gid 65532 --no-create-home --home-dir /tmp \
        --shell /usr/sbin/nologin robium
WORKDIR /app
RUN python -m pip install --no-cache-dir "uv==${UV_VERSION}"
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY test-assets ./test-assets
RUN uv sync --frozen --no-dev
ENV VLA_RUNTIME_MODE=fake \
    VLA_GATEWAY_PORT=8765 \
    HOME=/tmp \
    USER=robium \
    LOGNAME=robium \
    PYTHONUNBUFFERED=1
EXPOSE 8765
USER 65532:65532
ENTRYPOINT ["/app/.venv/bin/python", "-m", "vla_pick_and_place.gateway"]

FROM ${CUDA_BUILDER} AS gpu-builder
ARG UV_VERSION
ARG LIBERO_REVISION
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    cmake git python3.10 python3.10-dev python3.10-venv python3-pip \
    && rm -rf /var/lib/apt/lists/*
RUN python3.10 -m pip install --no-cache-dir "uv==${UV_VERSION}"
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --python python3.10 --frozen --no-dev --extra gpu --no-install-project
COPY src ./src
COPY test-assets ./test-assets
RUN uv sync --python python3.10 --frozen --no-dev --extra gpu
RUN git init /opt/libero \
    && git -C /opt/libero remote add origin https://github.com/huggingface/LIBERO.git \
    && git -C /opt/libero fetch --depth 1 origin "${LIBERO_REVISION}" \
    && git -C /opt/libero checkout --detach FETCH_HEAD \
    && test "$(git -C /opt/libero rev-parse HEAD)" = "${LIBERO_REVISION}"
RUN mkdir -p /app/.venv/lib/python3.10/site-packages/libero/libero/assets \
    && cp -a /opt/libero/libero/libero/assets/. \
        /app/.venv/lib/python3.10/site-packages/libero/libero/assets/

FROM ${CUDA_RUNTIME} AS gpu
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libegl1 libgl1 libglib2.0-0 libosmesa6 python3.10 python3.10-venv \
    && groupadd --gid 65532 robium \
    && useradd --uid 65532 --gid 65532 --no-create-home --home-dir /tmp \
        --shell /usr/sbin/nologin robium \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=gpu-builder /app/.venv /app/.venv
COPY --from=gpu-builder /app/src /app/src
COPY --from=gpu-builder /app/test-assets /app/test-assets
COPY --from=gpu-builder /opt/libero /opt/libero
COPY docker/libero-config.yaml /app/libero-config/config.yaml
ENV VLA_RUNTIME_MODE=real \
    VLA_CHECKPOINT_PATH=/models/pi05-libero-v044 \
    VLA_STAGED_CHECKPOINT_PATH=/tmp/pi05-libero-v044 \
    VLA_GATEWAY_PORT=8765 \
    MUJOCO_GL=egl \
    LIBERO_CONFIG_PATH=/app/libero-config \
    HOME=/tmp \
    USER=robium \
    LOGNAME=robium \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    PYTHONUNBUFFERED=1
EXPOSE 8765
USER 65532:65532
ENTRYPOINT ["/app/.venv/bin/python", "-m", "vla_pick_and_place.startup"]
