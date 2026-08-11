#!/usr/bin/env bash
# Foxglove WebSocket handshake probe. Usage: check_ws.sh http://<robot-ip>:8765
# foxglove_bridge 3.x (Foxglove-SDK based, e.g. 3.4.2 on this robot) expects the
# subprotocol "foxglove.sdk.v1"; pre-SDK builds used "foxglove.websocket.v1".
# Override with WS_SUBPROTOCOL if the installed version ever changes.
set -uo pipefail
BASE="${1:?usage: check_ws.sh <base-url>}"
SUB="${WS_SUBPROTOCOL:-foxglove.sdk.v1}"
RESP=$(curl -s -i -N --http1.1 --max-time 15 \
  -H "Connection: Upgrade" -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Version: 13" \
  -H "Sec-WebSocket-Key: $(openssl rand -base64 16)" \
  -H "Sec-WebSocket-Protocol: $SUB" \
  "$BASE/" | head -5)
echo "$RESP" | head -1
if echo "$RESP" | head -1 | grep -q " 101 "; then
  echo "WS HANDSHAKE OK"; exit 0
else
  echo "WS HANDSHAKE FAIL"; exit 1
fi
