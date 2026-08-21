# The demo container: the session gateway + Gradio/Rerun UI on :8765.
#
# The native `./app run` path is the supported one — this image exists so the
# same workspace can be served somewhere without a Mac. CPU-only by design:
# Docker on macOS cannot see MPS, and nothing in this milestone runs a policy
# anyway (see src/vla_pick_and_place/policy/controllers.py).
#
# Build via `make demo-image`. No secret is needed: the environment is a
# public pip package and the demonstration dataset is a public Hub repo.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      libgl1 libegl1 libosmesa6 git \
    && rm -rf /var/lib/apt/lists/*

# osmesa: pure-CPU software GL — the only MuJoCo backend that needs no GPU and
# no display. The bake step below actually renders, so a broken GL fails the
# BUILD rather than a visitor's session.
ENV MUJOCO_GL=osmesa \
    VLA_DEVICE=cpu \
    HF_HOME=/opt/hf \
    PORT=8765

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir uv && uv pip install --system -e .

# Bake by running the real boot path once: builds the pinned environment,
# resets it, renders both cameras, and pulls the pinned demonstration episode
# into HF_HOME. A schema or GL failure surfaces here, at build time.
RUN python -m vla_pick_and_place.run contract \
 && python -m vla_pick_and_place.run dataset-check

# Runtime never touches the Hub: the pinned revision was fetched above, and a
# Hub outage must not be able to break a session.
ENV HF_HUB_OFFLINE=1

EXPOSE 8765
CMD ["python", "-m", "vla_pick_and_place.demo.gateway"]
