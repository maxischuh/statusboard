# My E-Ink Statusboard

## Overview
- Python slideshow for the Waveshare 7.5" e-paper (V2) panel.
- Rotates between local weather data (Open-Meteo) and an MVV departure monitor.
- Updates a subtle progress bar every second so the panel shows activity.
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
3. Make sure the Python modules (`requests`, `Pillow`, `selenium`, `RPi.GPIO`, `spidev`) are available. `setup.sh` installs the system packages on Raspberry Pi OS.
4. Run the slideshow manually for a quick check: `python3 status.py`.

## Run on Boot (systemd)
1. Ensure `local_settings.py` is in place and working.
2. Install the service: `sudo ./install_service.sh`.
3. Check status: `sudo systemctl status statusboard.service`.
4. Disable or remove later with `sudo systemctl disable --now statusboard.service`.

## Hardware
- [7.5" Waveshare e-Paper (HD)](https://www.waveshare.com/wiki/7.5inch_HD_e-Paper_HAT)
- [Raspberry Pi Zero 2 (WH)](https://www.raspberrypi.com/products/raspberry-pi-zero-2-w/)
- Micro-USB power supply

## Data Sources
- [Open-Meteo (DWD ICON)](https://open-meteo.com/en/docs/dwd-api?latitude=48&longitude=11) for weather data.
- [MVV Departure Monitor](https://www.mvv-muenchen.de/fahrplanauskunft/fuer-entwickler/homepage-services/index.html) for public transport departures.
