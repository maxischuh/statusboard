#!/usr/bin/env bash
set -euo pipefail

# --------------------------------------
# Raspberry Pi / Debian (bookworm/trixie) setup for:
# - Waveshare 7.5" epaper demos
# - Open-Meteo (requests)
# - Selenium + Chromium + Chromedriver
# --------------------------------------

# ---- detect target user for group membership ----
TARGET_USER="${SUDO_USER:-$USER}"

echo "==> Updating and upgrading apt index…"
apt-get update -y
apt-get upgrade -y

# ---- helper to check if a package name exists in repo ----
has_pkg() {
  apt-cache show "$1" > /dev/null 2>&1
}

# ---- pick Chromium package names for this distro ----
CHROMIUM_PKG=""
CHROMEDRIVER_PKG=""
if has_pkg chromium; then
  CHROMIUM_PKG="chromium"
elif has_pkg chromium-browser; then
  CHROMIUM_PKG="chromium-browser"
fi

if has_pkg chromium-driver; then
  CHROMEDRIVER_PKG="chromium-driver"
elif has_pkg chromedriver; then
  CHROMEDRIVER_PKG="chromedriver"
fi

echo "==> Installing system packages…"
# Core Python + libs used in your scripts
apt-get install -y \
  python3 python3-pip python3-venv \
  python3-requests python3-pil \
  python3-rpi.gpio python3-spidev \
  fonts-dejavu-core \
  ${CHROMIUM_PKG:+$CHROMIUM_PKG} \
  ${CHROMEDRIVER_PKG:+$CHROMEDRIVER_PKG} \
  python3-selenium

# ---- enable SPI if not already ----
CONFIG1="/boot/firmware/config.txt"
CONFIG2="/boot/config.txt"
CFG="${CONFIG1}"
[ -f "$CONFIG1" ] || CFG="$CONFIG2"

if [ -f "$CFG" ]; then
  if ! grep -qE '^\s*dtparam=spi=on' "$CFG"; then
    echo "==> Enabling SPI in $CFG"
    printf "\n# enable SPI for e-Paper\n dtparam=spi=on\n" >> "$CFG"
    SPI_ENABLED="1"
  else
    SPI_ENABLED="0"
  fi
else
  echo "!! Could not find /boot config to enable SPI automatically. Skipping."
  SPI_ENABLED="0"
fi

# ---- add user to spi/gpio groups (so you can run without sudo) ----
echo "==> Adding $TARGET_USER to spi,gpio groups…"
usermod -aG spi,gpio "$TARGET_USER" || true

# ---- sanity checks ----
echo "==> Verifying Python imports…"
python3 - <<'PY'
import sys
mods = ["RPi.GPIO","spidev","PIL","requests","selenium"]
ok = True
for m in mods:
    try:
        __import__(m)
        print("  [OK] import", m)
    except Exception as e:
        ok = False
        print("  [FAIL] import", m, "->", e)
sys.exit(0 if ok else 1)
PY

# ---- show Chromium/driver paths if present ----
if command -v chromium >/dev/null 2>&1; then
  echo "Chromium:" "$(command -v chromium)"
elif command -v chromium-browser >/dev/null 2>&1; then
  echo "Chromium:" "$(command -v chromium-browser)"
fi

if [ -x /usr/bin/chromedriver ]; then
  echo "Chromedriver: /usr/bin/chromedriver"
elif command -v chromedriver >/dev/null 2>&1; then
  echo "Chromedriver:" "$(command -v chromedriver)"
fi

echo
echo "✅ Setup complete."
if [ "${SPI_ENABLED}" = "1" ]; then
  echo "   SPI was enabled; a reboot is recommended."
fi
echo "   User '$TARGET_USER' was added to 'spi' and 'gpio'. Log out/in (or reboot) for it to take effect."
echo
echo "You can now run your slideshow script, e.g.:"
echo "  sudo python3 status_slideshow_dots3.py"