#!/bin/sh
set -e
: "${ROBOT_HOST:=192.0.2.10}"
: "${ROBOT_WS_PORT:=8765}"
: "${WEBCAM_STREAM_URL:=}"
: "${FOXGLOVE_LAYOUT_ID:=}"
export ROBOT_HOST ROBOT_WS_PORT WEBCAM_STREAM_URL FOXGLOVE_LAYOUT_ID
envsubst < /usr/share/nginx/html/env.js.tmpl > /usr/share/nginx/html/env.js
exec nginx -g 'daemon off;'
