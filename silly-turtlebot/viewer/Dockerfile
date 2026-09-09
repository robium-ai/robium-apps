# syntax=docker/dockerfile:1

# Lichtblick currently publishes an amd64 image, but the browser bundle copied
# from it is architecture-independent and runs from the multi-arch Python image.
FROM --platform=linux/amd64 ghcr.io/lichtblick-suite/lichtblick@sha256:e29673ab12265fe84a62fed0835606d8789168fe9b3395a2997d97f002ed1e9d AS lichtblick

FROM node:22-bookworm-slim AS controls
WORKDIR /extension
COPY silly-turtlebot/lichtblick-extension/package.json silly-turtlebot/lichtblick-extension/package-lock.json ./
RUN npm ci
COPY silly-turtlebot/lichtblick-extension/ ./
RUN npm run package

FROM python:3.12-slim-bookworm
COPY --from=lichtblick /src /opt/lichtblick
COPY silly-turtlebot/lichtblick/layout.json /opt/lichtblick/layout.json
COPY --from=controls /extension/robium.silly-turtlebot-controls-0.1.0.foxe /opt/lichtblick/robium/dashboard.foxe
COPY silly-turtlebot/lichtblick-extension/package.json /opt/lichtblick/robium/package.json
COPY silly-turtlebot/lichtblick-extension/README.md /opt/lichtblick/robium/README.md
COPY silly-turtlebot/lichtblick-extension/CHANGELOG.md /opt/lichtblick/robium/CHANGELOG.md
COPY shared/lichtblick-dashboard/deploy/preinstall-extension.mjs /opt/lichtblick/robium/preinstall-extension.mjs
COPY silly-turtlebot/simulation/viz_server.py /viz_server.py
COPY silly-turtlebot/simulation/bundle_extension.py /bundle_extension.py
RUN python3 /bundle_extension.py \
      /opt/lichtblick/index.html /opt/lichtblick/robium/dashboard.foxe \
 && cp /opt/lichtblick/index.html /opt/lichtblick/index.template.html

EXPOSE 8080
ENTRYPOINT ["python3", "/viz_server.py"]
