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
