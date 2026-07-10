# My E-Ink Statusboard

## Overview
- Python dashboard for the Waveshare 7.5" e-paper (V2) panel.
- Shows current local weather, smooth 12-hour temperature and precipitation trends, and structured MVV departure data on one integrated screen.
- Uses clean full-waveform updates in quality mode and powers the panel down between refreshes.
- Private details (timezone, coordinates, MVV embed) live in `local_settings.py`, which stays out of git.

## Repository Layout
- `status.py` – main slideshow.
- `local_settings.example.py` – template for your private configuration (copy to `local_settings.py`).
- `lib/` – bundled Waveshare display driver (`waveshare_epd`).
- `pic/` – static assets such as `Font.ttc`.
- `setup.sh` – installs system packages/drivers on Raspberry Pi OS.
- `install_service.sh` – registers `status.py` as a systemd service for auto-start on boot.

## Getting Started
1. `cp local_settings.example.py local_settings.py` and edit the new file:
   - Set `TZ`, `LAT`, `LON`.
   - Paste your MVV monitor HTML snippet (or leave empty to skip MVV).
2. (Optional) Prepare the Pi: `sudo ./setup.sh`.
3. Make sure the Python modules (`requests`, `Pillow`, `RPi.GPIO`, `spidev`) are available. `setup.sh` installs the system packages on Raspberry Pi OS.
4. Run the slideshow manually for a quick check: `python3 status.py`.

## Preview Layouts
Generate deterministic PNG previews without display hardware or network access:

```sh
python3 status.py --preview
```

By default this writes exact `800x480` panel images and larger framed screen simulations to `previews/` for Munich. Use `python3 status.py --preview path/to/output` to choose another directory.

Available preview cities:

```sh
python3 status.py --preview --preview-city munich
python3 status.py --preview frankfurt-previews --preview-city frankfurt-am-main
```

## Long-Running Stability
- The board keeps the last successful weather and MVG data in memory when a refresh fails.
- MVG departures are fetched as structured EFA JSON rows, cached in memory, and retried with backoff during outages.
- Logging is intentionally compact: startup, periodic heartbeat, bounded MVV success logs, warnings, and display recovery events without dumping API payloads.
- The dashboard redraws on actual minute changes and coalesces clock and data changes into a single refresh when possible.
- Quality mode disables the pale full-screen partial waveform, limits display updates to once every five minutes, clears before redrawing, uses the controller's specified +/-15 V source drive, and powers the panel down immediately afterward.
- The Raspberry Pi onboard status LEDs are turned off at startup; the systemd installer also runs that LED shutdown once as root before the service drops to the dashboard user.
- The systemd service restarts the process if it exits unexpectedly, without requiring a Raspberry Pi reboot.

## Run on Boot (systemd)
1. Ensure `local_settings.py` is in place and working.
2. Install the service: `sudo ./install_service.sh`.
3. Check status: `sudo systemctl status statusboard.service`.
4. Disable or remove later with `sudo systemctl disable --now statusboard.service`.

## Full Display Reset
Use the standalone reset utility to run the hardware reset sequence, clear the
panel to white with a full waveform, and power the driver board down cleanly:

```sh
sudo systemctl stop statusboard.service
python3 reset_display.py
sudo systemctl start statusboard.service
```

The dashboard service must not access the SPI display while the reset runs. The
utility detects a running service and exits with instructions unless the unsafe
`--ignore-running-service` diagnostic option is supplied.

## Contrast Diagnostic
The diagnostic uses a one-bit image, a clean full refresh, and immediate power
down, so it isolates the panel drive from dashboard rendering and partial-update
artifacts:

```sh
sudo systemctl stop statusboard.service
python3 display_diagnostic.py --profile full
```

The large left rectangle and bottom band must be uniformly deep black. If they
remain gray, check the hardware before tuning software voltages:

1. The driver HAT `Display Config` switch must be at `B / 0.47R` for this 7.5-inch panel.
2. The interface switch must be in 4-line SPI mode because the driver uses a separate D/C signal.
3. Confirm the rear panel label says V2. Panels sold before September 2023 require Waveshare's `7.5V2_old` waveform instead.
4. Check for a stable supply, short display cable, and at least 2.5 V at the panel under refresh load.

To inspect the generated pattern without hardware, run
`python3 display_diagnostic.py --preview diagnostic-pattern.png`.

## Hardware
- [7.5" Waveshare e-Paper HAT V2 (800×480)](https://www.waveshare.com/wiki/7.5inch_e-Paper_HAT_Manual)
- [Raspberry Pi Zero 2 (WH)](https://www.raspberrypi.com/products/raspberry-pi-zero-2-w/)
- Micro-USB power supply

## Data Sources
- [Open-Meteo (DWD ICON)](https://open-meteo.com/en/docs/dwd-api?latitude=48&longitude=11) for weather data.
- [MVV EFA](https://www.mvv-muenchen.de/fahrplanauskunft/fuer-entwickler/homepage-services/index.html) for public transport departures.
