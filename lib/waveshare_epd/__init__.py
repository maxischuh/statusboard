"""Local copy of the Waveshare EPD driver so we can import without extra installs."""

from . import epd7in5_V2, epdconfig  # re-export modules for convenience

__all__ = ["epd7in5_V2", "epdconfig"]
