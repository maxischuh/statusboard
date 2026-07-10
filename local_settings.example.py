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

# Optional display readability tuning. Clock-only updates use partial refreshes;
# a full refresh is promoted after this many partial updates, after FULL_REFRESH
# seconds, or after CONTENT_FULL_REFRESH seconds when weather/MVV content changes.
MAX_PARTIAL_REFRESHES = 5
FULL_REFRESH = 10 * 60
CONTENT_FULL_REFRESH = 5 * 60

# Use Waveshare's alternate VCOM initialization for panels whose black pixels
# otherwise look gray. Disable only if your particular panel behaves worse.
DISPLAY_HIGH_CONTRAST = True

# Optional hardware setting: disable the Raspberry Pi onboard status LEDs at startup.
DISABLE_RPI_STATUS_LEDS = True
