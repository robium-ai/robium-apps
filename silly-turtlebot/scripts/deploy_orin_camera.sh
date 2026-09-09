#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: $0 USER@ORIN_IP" >&2
  exit 2
fi

target=$1
app_root="$(cd "$(dirname "$0")/.." && pwd)"
remote_root=silly-turtlebot

ssh -o BatchMode=yes -o ConnectTimeout=12 "$target" \
  "mkdir -p '${remote_root}/orin'"
rsync -az --delete "${app_root}/orin/" "${target}:${remote_root}/orin/"
ssh -o BatchMode=yes -o ConnectTimeout=12 "$target" \
  "cd '${remote_root}/orin' && docker compose up -d --build --force-recreate oakd tts"

echo "OAK-D + Kokoro TTS deployed at ${target}"
echo "Camera health: http://ORIN_IP:8081/health"
echo "Speech health: http://ORIN_IP:8082/health"
