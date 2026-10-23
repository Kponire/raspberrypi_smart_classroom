#!/usr/bin/env bash
set -euo pipefail
# Smart Classroom — Pi kiosk setup (run once on a fresh Raspberry Pi OS)
# - Installs deps, enables kiosk autostart on boot, fullscreen on the TV.
#
# Usage:
#   chmod +x pi-setup.sh
#   ./pi-setup.sh
# Then edit .env:  cp .env.example .env  && nano .env

HERE="$(cd "$(dirname "$0")" && pwd)"
PY=python3

echo "==> Installing system packages (chromium, unclutter, pip deps)…"
if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y chromium-browser unclutter python3-pip python3-tk python3-psutil 2>/dev/null || \
  sudo apt-get install -y chromium python3-pip python3-tk 2>/dev/null || true
fi

echo "==> Python deps…"
$PY -m pip install --upgrade pip
$PY -m pip install -r "$HERE/requirements.txt" 2>/dev/null || pip install -r "$HERE/requirements.txt"

if [ ! -f "$HERE/.env" ]; then
  cp "$HERE/.env.example" "$HERE/.env"
  echo "==> Created .env — EDIT IT: nano $HERE/.env (set API_URL to your backend LAN IP, e.g. http://192.168.1.50:3000)"
fi

# Autostart: LXDE + systemd (either will catch it; one suffices on Pi OS Bookworm+)
AUTOSTART_DIR="$HOME/.config/autostart"
mkdir -p "$AUTOSTART_DIR"
cat > "$AUTOSTART_DIR/smart-classroom.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Smart Classroom TV
Exec=$PY $HERE/main.py
X-GNOME-Autostart-enabled=true
EOF

SERVICE="$HOME/.config/systemd/user/smart-classroom.service"
mkdir -p "$(dirname "$SERVICE")"
cat > "$SERVICE" <<EOF
[Unit]
Description=Smart Classroom TV (Tkinter kiosk)
After=graphical-session.target

[Service]
Type=simple
WorkingDirectory=$HERE
ExecStart=$PY $HERE/main.py
Restart=always
RestartSec=3
Environment=DISPLAY=:0

[Install]
WantedBy=default.target
EOF

if command -v systemctl >/dev/null 2>&1; then
  systemctl --user daemon-reload || true
  systemctl --user enable smart-classroom.service || true
  echo "==> Enabled systemd user service: smart-classroom.service"
fi

echo ""
echo "Done. Next:"
echo "  1) nano $HERE/.env   # set API_URL to backend LAN IP, and CLASSROOM_ID/DEVICE_ID if you have them"
echo "  2) Reboot or run:  $PY $HERE/main.py"
echo "  TV tip: the app is fullscreen; Esc exits fullscreen, F11 toggles."
