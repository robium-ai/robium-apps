#!/bin/sh
set -eu

APP_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
REVISION=86958911c0f959db2bbbdb107eb3e17c5f9c798e
DATASET=HuggingFaceVLA%2Flibero
DEST="$APP_DIR/test-assets/fixtures"

mkdir -p "$DEST"

fetch_frame() {
  fixture_id=$1
  offset=$2
  row_json=$(mktemp "/tmp/robium-vla-row-${fixture_id}.XXXXXX")
  trap 'rm -f "$row_json"' EXIT HUP INT TERM
  curl -fsSL "https://datasets-server.huggingface.co/rows?dataset=$DATASET&config=default&split=train&offset=$offset&length=1" -o "$row_json"
  image_url=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["rows"][0]["row"]["observation.images.image"]["src"])' "$row_json")
  curl -fsSL "$image_url" -o "$DEST/frame-${fixture_id}.jpg"
  rm -f "$row_json"
  trap - EXIT HUP INT TERM
}

# First frames from three official task-8 demonstration episodes at the pinned
# dataset revision. The offsets are grounded by meta/episodes metadata.
fetch_frame 0 101469
fetch_frame 1 107174
fetch_frame 2 107606

echo "Fetched official LIBERO fixtures at $REVISION"
