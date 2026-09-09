# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:0.11.29 AS uv
FROM python:3.12-slim-bookworm

COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY silly-turtlebot/pyproject.toml silly-turtlebot/uv.lock silly-turtlebot/README.md ./
COPY silly-turtlebot/src ./src
RUN uv sync --locked --no-dev

ENV PATH="/app/.venv/bin:${PATH}"
EXPOSE 8090
CMD ["silly-turtlebot", "serve", "--host", "0.0.0.0", "--port", "8090"]
