#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
reference_tools="${STACKCHAN_TOOLCHAIN:-../../robium-apps/stackchan-er2/.arduino}"
mkdir -p .local/build
python3 - "$reference_tools" <<'PY'
import json
from pathlib import Path
import sys
base = Path(sys.argv[1]).resolve()
if not (base / 'data/packages/esp32/hardware/esp32/3.3.11').is_dir():
    raise SystemExit('Pinned ESP32 toolchain missing. Run stackchan-er2/app firmware-setup, or set STACKCHAN_TOOLCHAIN.')
Path('.local/arduino.yaml').write_text('directories:\n' + ''.join(
    f'  {key}: {json.dumps(str(base/value))}\n'
    for key, value in [('data', 'data'), ('downloads', 'downloads'), ('user', 'user')]))
PY
fqbn='esp32:esp32:m5stack_cores3:USBMode=hwcdc,CDCOnBoot=cdc,FlashSize=16M,PartitionScheme=app3M_fat9M_16MB,PSRAM=enabled'
case "${1:-build}" in
  build) arduino-cli compile --config-file .local/arduino.yaml --fqbn "$fqbn" --output-dir .local/build firmware/stackchan_camera ;;
  flash)
    test -s .local/stackchan-before-camera.bin || { echo 'Save a full device restore image first (.local/stackchan-before-camera.bin).'; exit 1; }
    arduino-cli upload --config-file .local/arduino.yaml --fqbn "$fqbn" --input-dir .local/build --port "${STACKCHAN_PORT:-/dev/cu.usbmodem101}" firmware/stackchan_camera
    ;;
  *) echo './firmware.sh build | flash'; exit 2 ;;
esac
