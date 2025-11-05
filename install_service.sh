#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Please run this script with sudo:"
  echo "  sudo $0"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_FILE="/etc/systemd/system/statusboard.service"
PYTHON_BIN="$(command -v python3)"

if [[ -z "${PYTHON_BIN}" ]]; then
  echo "python3 not found on PATH. Install it before continuing." >&2
  exit 1
fi

if [[ ! -f "${SCRIPT_DIR}/status.py" ]]; then
  echo "Cannot find status.py in ${SCRIPT_DIR}. Run this script from the repository root." >&2
  exit 1
fi

if [[ ! -f "${SCRIPT_DIR}/local_settings.py" ]]; then
  echo "local_settings.py is missing. Copy local_settings.example.py and customise it first." >&2
  exit 1
fi

SERVICE_USER="${SUDO_USER:-$(logname 2>/dev/null || echo pi)}"

cat <<EOF > "${SERVICE_FILE}"
[Unit]
Description=E-Ink Statusboard
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${SCRIPT_DIR}
Environment=PYTHONUNBUFFERED=1
ExecStart=${PYTHON_BIN} ${SCRIPT_DIR}/status.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SupplementaryGroups=spi gpio

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable statusboard.service
systemctl restart statusboard.service

echo "statusboard.service installed for user '${SERVICE_USER}'."
echo "Use 'sudo systemctl status statusboard.service' to check its state."
