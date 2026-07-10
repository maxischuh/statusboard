#!/usr/bin/env python3
"""Fully reset, clear, and power down the Waveshare e-paper display."""

import argparse
import logging
import shutil
import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
LIB_DIR = BASE_DIR / "lib"
SERVICE_NAME = "statusboard.service"

if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

try:
    import local_settings as _local_settings  # type: ignore
except ImportError:
    _local_settings = None


def display_high_contrast_enabled() -> bool:
    if _local_settings is None:
        return True
    return bool(getattr(_local_settings, "DISPLAY_HIGH_CONTRAST", True))


def service_is_active(service_name=SERVICE_NAME) -> bool:
    if shutil.which("systemctl") is None:
        return False
    result = subprocess.run(
        ["systemctl", "is-active", "--quiet", service_name],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def reset_panel(epd) -> None:
    """Run the panel's hardware reset and a full-waveform white clear."""
    init_result = epd.init()
    if init_result not in (None, 0):
        raise RuntimeError(f"Display initialisation failed with status {init_result}")
    epd.Clear()


def power_down_panel(epd, epdconfig) -> None:
    try:
        epd.sleep()
    except Exception:
        logging.exception("Display sleep failed; forcing the driver board power off")
        epdconfig.module_exit()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Perform a full hardware reset, clear the display to white, and power it down."
    )
    parser.add_argument(
        "--ignore-running-service",
        action="store_true",
        help="Reset even if statusboard.service is active (unsafe; use only for diagnostics).",
    )
    parser.add_argument(
        "--standard-contrast",
        action="store_true",
        help="Use Waveshare's standard VCOM setting instead of the configured high-contrast setting.",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if not args.ignore_running_service and service_is_active():
        logging.error("%s is running; stop it before resetting the display.", SERVICE_NAME)
        logging.error("Run: sudo systemctl stop %s", SERVICE_NAME)
        logging.error("After the reset: sudo systemctl start %s", SERVICE_NAME)
        return 2

    from waveshare_epd import epd7in5_V2

    high_contrast = display_high_contrast_enabled() and not args.standard_contrast
    epd = epd7in5_V2.EPD(high_contrast=high_contrast)
    logging.info("Starting full display reset (high_contrast=%s)", high_contrast)

    try:
        reset_panel(epd)
        logging.info("Full-waveform clear completed; display is white")
    finally:
        power_down_panel(epd, epd7in5_V2.epdconfig)

    logging.info("Display reset complete and driver board powered down")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
