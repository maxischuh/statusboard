#!/usr/bin/env python3
"""Display a one-bit test pattern that isolates panel contrast problems."""

import argparse
import logging
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from reset_display import SERVICE_NAME, power_down_panel, service_is_active


BASE_DIR = Path(__file__).resolve().parent
LIB_DIR = BASE_DIR / "lib"
FONT_PATH = BASE_DIR / "pic" / "Font.ttc"
WIDTH, HEIGHT = 800, 480

if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))


def load_font(size):
    return ImageFont.truetype(str(FONT_PATH), size)


def create_contrast_pattern():
    image = Image.new("1", (WIDTH, HEIGHT), 255)
    draw = ImageDraw.Draw(image)
    title_font = load_font(42)
    body_font = load_font(25)
    label_font = load_font(19)

    draw.rectangle((0, 0, WIDTH - 1, HEIGHT - 1), outline=0, width=2)

    # Large uniform fields distinguish panel drive problems from font rendering.
    draw.rectangle((16, 16, 390, 220), fill=0)
    draw.text((42, 68), "SOLID BLACK", font=title_font, fill=255)
    draw.text((65, 132), "must be deep black", font=body_font, fill=255)

    draw.rectangle((410, 16, 783, 220), outline=0, width=4)
    draw.text((445, 68), "SOLID WHITE", font=title_font, fill=0)
    draw.text((470, 132), "must be clean white", font=body_font, fill=0)

    draw.text((16, 238), "Line weights", font=label_font, fill=0)
    line_y = 272
    for width in (1, 2, 4, 8):
        draw.line((145, line_y, 390, line_y), fill=0, width=width)
        draw.text((402, line_y - 10), f"{width}px", font=label_font, fill=0)
        line_y += 36

    draw.text((510, 238), "Alternating pixels", font=label_font, fill=0)
    for y in range(270, 404, 16):
        for x in range(510, 784, 16):
            if ((x - 510) // 16 + (y - 270) // 16) % 2 == 0:
                draw.rectangle((x, y, x + 15, y + 15), fill=0)

    draw.rectangle((16, 420, 783, 464), fill=0)
    draw.text(
        (32, 427),
        "ONE-BIT FULL REFRESH - NO GRAY PIXELS",
        font=body_font,
        fill=255,
    )
    return image


def display_pattern(epd, epdconfig, image):
    try:
        init_result = epd.init()
        if init_result not in (None, 0):
            raise RuntimeError(f"Display initialisation failed with status {init_result}")
        epd.Clear()
        epd.display(epd.getbuffer(image))
    finally:
        power_down_panel(epd, epdconfig)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Show a full-refresh pattern for diagnosing e-paper contrast."
    )
    parser.add_argument(
        "--profile",
        choices=("full", "legacy"),
        default="full",
        help="Source voltage profile: full is the specified +/-15 V; legacy is +10.4/-7.0 V.",
    )
    parser.add_argument(
        "--preview",
        metavar="PNG",
        help="Write the one-bit test pattern to PNG without accessing display hardware.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    pattern = create_contrast_pattern()

    if args.preview:
        output = Path(args.preview)
        output.parent.mkdir(parents=True, exist_ok=True)
        pattern.save(output)
        logging.info("Diagnostic preview written to %s", output)
        return 0

    if service_is_active():
        logging.error("%s is running; stop it before using the diagnostic.", SERVICE_NAME)
        logging.error("Run: sudo systemctl stop %s", SERVICE_NAME)
        return 2

    from waveshare_epd import epd7in5_V2

    full_voltage = args.profile == "full"
    logging.info("Hardware check: Display Config=B/0.47R and interface=4-line SPI")
    logging.info(
        "Displaying contrast pattern with %s source profile",
        "+/-15 V" if full_voltage else "legacy +10.4/-7.0 V",
    )
    epd = epd7in5_V2.EPD(high_contrast=full_voltage)
    display_pattern(epd, epd7in5_V2.epdconfig, pattern)
    logging.info("Diagnostic complete; panel powered down with the pattern retained")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
