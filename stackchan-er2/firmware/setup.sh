#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

arduino_root="$PWD/.arduino"
config_dir="$arduino_root/config"
config_file="$config_dir/arduino-cli.yaml"
mkdir -p "$config_dir" "$arduino_root/data" "$arduino_root/downloads" "$arduino_root/user"

if [ ! -f "$config_file" ]; then
  arduino-cli config init --dest-dir "$config_dir" >/dev/null
fi
arduino-cli config set directories.data "$arduino_root/data" --config-file "$config_file" >/dev/null
arduino-cli config set directories.downloads "$arduino_root/downloads" --config-file "$config_file" >/dev/null
arduino-cli config set directories.user "$arduino_root/user" --config-file "$config_file" >/dev/null
arduino-cli config set board_manager.additional_urls \
  https://espressif.github.io/arduino-esp32/package_esp32_index.json \
  --config-file "$config_file" >/dev/null
arduino-cli config set library.enable_unsafe_install true \
  --config-file "$config_file" >/dev/null

arduino-cli core update-index --config-file "$config_file"
arduino-cli core install esp32:esp32@3.3.11 --config-file "$config_file"
arduino-cli lib update-index --config-file "$config_file"
arduino-cli lib install \
  M5Unified@0.2.20 ArduinoJson@7.4.3 IRremoteESP8266@2.9.0 M5Unit-NFC@0.1.1 \
  --config-file "$config_file"
arduino-cli lib install --git-url \
  https://github.com/m5stack/StackChan-BSP.git#1.1.0 \
  --config-file "$config_file"
