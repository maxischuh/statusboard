"""
Local configuration for the statusboard.

Copy this file to `local_settings.py` and adjust the values for your setup.
The real file is ignored by git so your private data stays local.
"""

# Timezone used for the board (run `timedatectl list-timezones` for options).
TZ = "Europe/Berlin"

# Coordinates for the weather API.
LAT = 48
LON = 11

# Paste the MVV monitor HTML snippet below. Leave it blank to skip MVV entirely.
# You can grab the snippet from https://www.mvv-muenchen.de/ by configuring your stop
# and copying the "embed" HTML.
MVV_HTML = ""

# Optional logging verbosity: DEBUG, INFO, WARNING, ERROR.
LOG_LEVEL = "INFO"

# Optional display readability tuning. Partial refresh is disabled by default
# because this panel's partial waveform produces pale text and must remain
# powered between updates. Quality mode performs a clean full refresh no more
# often than every five minutes, then immediately powers the panel down.
PARTIAL_REFRESH_ENABLED = False
DISPLAY_MIN_REFRESH = 5 * 60

# These settings apply only when PARTIAL_REFRESH_ENABLED is True.
MAX_PARTIAL_REFRESHES = 5
FULL_REFRESH = 10 * 60
CONTENT_FULL_REFRESH = 5 * 60

# Use the +/-15 V source levels specified by the controller datasheet and used
# by Waveshare's C, STM32, and Arduino drivers. False restores the lower,
# asymmetric voltage pair from Waveshare's Python driver for comparison only.
DISPLAY_HIGH_CONTRAST = True

# Optional hardware setting: disable the Raspberry Pi onboard status LEDs at startup.
DISABLE_RPI_STATUS_LEDS = True
