"""Compile and upload the bridge firmware to the mCore board.

Both steps shell out to arduino-cli. That is worth stating plainly because this
file briefly did something much cleverer: it spoke STK500v1 to the bootloader
directly, to work around uploads that failed with `not in sync: resp=0x00`.

The workaround was aimed at the wrong target. Those failures came from the
mBot's Bluetooth module sharing the D0/D1 upload UART - two drivers on one RX
pin - and no amount of host-side protocol handling fixes a contended wire. With
the module unplugged, stock avrdude uploads first time, every time. The clever
version is gone; what remains is the standard toolchain plus an ICSP path for
boards whose module is soldered on and cannot be removed.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

FIRMWARE_DIR = Path(__file__).resolve().parents[2] / "firmware" / "mbot_bridge"
BUILD_DIR = Path(__file__).resolve().parents[2] / "build"
FQBN = "arduino:avr:uno"  # the mCore is an ATmega328P Uno clone


class FlashError(RuntimeError):
    pass


# Programming over SPI instead of the serial port, for an mBot whose Bluetooth
# module is soldered to the board. ICSP does not touch D0/D1 at all.
ISP_PROGRAMMERS = {
    # A spare Arduino running the stock "ArduinoISP" example sketch.
    "arduino-as-isp": ["-c", "stk500v1", "-b", "19200"],
    "usbasp": ["-c", "usbasp"],
    "usbtiny": ["-c", "usbtiny"],
}

# Uno / optiboot fuses, so a bootloader written back is actually entered on
# reset rather than skipped.
UNO_FUSES = {"lfuse": "0xFF", "hfuse": "0xDE", "efuse": "0xFD"}


def _require_arduino_cli() -> None:
    if shutil.which("arduino-cli") is None:
        raise FlashError(
            "arduino-cli not found. Install it with 'brew install arduino-cli', "
            "then 'arduino-cli core install arduino:avr'."
        )


def find_avrdude() -> tuple[Path, Path]:
    """The avrdude and config that came with the AVR core, for the ICSP path."""
    root = Path.home() / "Library/Arduino15/packages/arduino/tools/avrdude"
    if not root.exists():  # Linux layout
        root = Path.home() / ".arduino15/packages/arduino/tools/avrdude"
    binaries = sorted(root.glob("*/bin/avrdude"))
    configs = sorted(root.glob("*/etc/avrdude.conf"))
    if not binaries or not configs:
        raise FlashError(
            "avrdude not found. Run 'arduino-cli core install arduino:avr' first."
        )
    return binaries[-1], configs[-1]


def compile_firmware(verbose: bool = True) -> Path:
    """Build the sketch and return the resulting hex file."""
    _require_arduino_cli()
    if verbose:
        print(f"compiling {FIRMWARE_DIR.name} for {FQBN}")
    result = subprocess.run(
        ["arduino-cli", "compile", "--fqbn", FQBN,
         "--output-dir", str(BUILD_DIR), str(FIRMWARE_DIR)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise FlashError(f"compile failed:\n{result.stdout}\n{result.stderr}")
    hex_path = BUILD_DIR / f"{FIRMWARE_DIR.name}.ino.hex"
    if not hex_path.exists():
        raise FlashError(f"compile produced no hex at {hex_path}")
    return hex_path


def flash(port: str, skip_compile: bool = False, verbose: bool = True) -> int:
    """Compile if needed, then upload over the serial port."""
    _require_arduino_cli()
    if not skip_compile:
        compile_firmware(verbose=verbose)

    if verbose:
        print(f"uploading to {port}")
    result = subprocess.run(
        ["arduino-cli", "upload", "-p", port, "--fqbn", FQBN, str(FIRMWARE_DIR)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise FlashError((result.stderr or result.stdout).strip())
    if verbose:
        print("firmware is on the board")
    return 0


def flash_isp(
    programmer: str,
    isp_port: str | None = None,
    skip_compile: bool = False,
    verbose: bool = True,
) -> int:
    """Write firmware over ICSP, bypassing the serial port entirely."""
    if programmer not in ISP_PROGRAMMERS:
        raise FlashError(
            f"Unknown programmer {programmer!r}. "
            f"Choose one of: {', '.join(sorted(ISP_PROGRAMMERS))}"
        )
    if programmer == "arduino-as-isp" and not isp_port:
        raise FlashError(
            "arduino-as-isp needs --isp-port, the serial port of the Arduino "
            "acting as the programmer (not the mBot's)."
        )

    # The image with the bootloader appended, so serial uploads keep working
    # afterwards. Writing the sketch alone would erase the bootloader and make
    # ICSP the only way in from then on.
    hex_path = BUILD_DIR / f"{FIRMWARE_DIR.name}.ino.with_bootloader.hex"
    if not skip_compile or not hex_path.exists():
        compile_firmware(verbose=verbose)
    if not hex_path.exists():
        raise FlashError(f"no bootloader-bearing image at {hex_path}")

    avrdude, config = find_avrdude()
    command = [str(avrdude), "-C", str(config), "-p", "atmega328p"]
    command += ISP_PROGRAMMERS[programmer]
    if isp_port:
        command += ["-P", isp_port]
    command += [f"-U{name}:w:{value}:m" for name, value in UNO_FUSES.items()]
    command += ["-U", f"flash:w:{hex_path}:i"]

    if verbose:
        print(f"programming over ICSP with {programmer}")
    result = subprocess.run(command, capture_output=True, text=True)
    if verbose:
        print((result.stderr or result.stdout).strip())
    if result.returncode != 0:
        raise FlashError(
            "ICSP programming failed. Check the six ICSP wires "
            "(MISO, MOSI, SCK, RESET, VCC, GND) and that the mBot is powered."
        )
    if verbose:
        print("firmware and bootloader are on the board")
    return 0
