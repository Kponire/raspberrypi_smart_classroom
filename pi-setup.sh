
#!/usr/bin/env bash
set -Eeuo pipefail

# ============================================================
# Smart Classroom — Raspberry Pi Setup
# Compatible with Raspberry Pi OS / Debian 13 (Trixie)
#
# Features:
#   - Installs system dependencies
#   - Creates a project-local Python virtual environment
#   - Installs requirements.txt into the virtual environment
#   - Creates .env from .env.example if needed
#   - Configures desktop autostart
#   - Optionally configures a systemd user service
#
# Usage:
#   chmod +x pi-setup.sh
#   ./pi-setup.sh
# ============================================================

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$HERE/.venv"
PYTHON="$VENV/bin/python"
PIP="$VENV/bin/pip"

SERVICE_NAME="smart-classroom.service"
AUTOSTART_DIR="$HOME/.config/autostart"
AUTOSTART_FILE="$AUTOSTART_DIR/smart-classroom.desktop"
SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_FILE="$SERVICE_DIR/$SERVICE_NAME"

echo
echo "============================================================"
echo " Smart Classroom Raspberry Pi Setup"
echo " Project directory: $HERE"
echo "============================================================"
echo

# ------------------------------------------------------------
# 1. Check operating system and package manager
# ------------------------------------------------------------

if ! command -v apt-get >/dev/null 2>&1; then
    echo "ERROR: apt-get was not found."
    echo "This script expects Raspberry Pi OS or Debian."
    exit 1
fi

if ! command -v sudo >/dev/null 2>&1; then
    echo "ERROR: sudo is required to install system packages."
    exit 1
fi

# ------------------------------------------------------------
# 2. Install system dependencies
# ------------------------------------------------------------

echo "==> Updating package lists..."

sudo apt-get update

echo "==> Installing system packages..."

# Try the Raspberry Pi OS Chromium package first.
# Fall back to the Debian package name if necessary.
if ! sudo apt-get install -y \
    python3-venv \
    python3-full \
    python3-pip \
    python3-tk \
    python3-psutil \
    unclutter; then
    echo "ERROR: Failed to install required system packages."
    exit 1
fi

if ! sudo apt-get install -y chromium-browser; then
    echo "Chromium-browser package unavailable; trying chromium..."
    if ! sudo apt-get install -y chromium; then
        echo "WARNING: Chromium could not be installed."
        echo "The Python/Tkinter application can still run if it does not need Chromium."
    fi
fi

# ------------------------------------------------------------
# 3. Check project files
# ------------------------------------------------------------

if [[ ! -f "$HERE/requirements.txt" ]]; then
    echo "ERROR: requirements.txt was not found in:"
    echo "  $HERE"
    exit 1
fi

if [[ ! -f "$HERE/main.py" ]]; then
    echo "ERROR: main.py was not found in:"
    echo "  $HERE"
    exit 1
fi

# ------------------------------------------------------------
# 4. Create Python virtual environment
# ------------------------------------------------------------

echo
echo "==> Preparing Python virtual environment..."

if [[ ! -x "$PYTHON" ]]; then
    python3 -m venv "$VENV"
fi

if [[ ! -x "$PYTHON" || ! -x "$PIP" ]]; then
    echo "ERROR: Python virtual environment creation failed."
    exit 1
fi

echo "Python interpreter: $PYTHON"

# ------------------------------------------------------------
# 5. Install Python dependencies
# ------------------------------------------------------------

echo
echo "==> Upgrading pip inside the virtual environment..."

"$PYTHON" -m pip install --upgrade pip

echo
echo "==> Installing project dependencies..."

"$PYTHON" -m pip install -r "$HERE/requirements.txt"

echo
echo "==> Python dependencies installed successfully."

# ------------------------------------------------------------
# 6. Create .env if it does not exist
# ------------------------------------------------------------

echo
echo "==> Checking environment configuration..."

if [[ ! -f "$HERE/.env" ]]; then
    if [[ -f "$HERE/.env.example" ]]; then
        cp "$HERE/.env.example" "$HERE/.env"
        echo "Created .env from .env.example"
    else
        echo "WARNING: .env.example was not found."
        echo "Create $HERE/.env manually using your application's required variables."
    fi
else
    echo "Existing .env found; leaving it unchanged."
fi

# ------------------------------------------------------------
# 7. Configure desktop autostart
# ------------------------------------------------------------

echo
echo "==> Configuring desktop autostart..."

mkdir -p "$AUTOSTART_DIR"

cat > "$AUTOSTART_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Smart Classroom TV
Comment=Launch the Smart Classroom application
Exec=$PYTHON $HERE/main.py
Path=$HERE
Terminal=false
X-GNOME-Autostart-enabled=true
EOF

chmod 644 "$AUTOSTART_FILE"

echo "Created: $AUTOSTART_FILE"

# ------------------------------------------------------------
# 8. Configure optional systemd user service
# ------------------------------------------------------------

echo
echo "==> Configuring systemd user service..."

mkdir -p "$SERVICE_DIR"

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Smart Classroom Application
After=graphical-session.target

[Service]
Type=simple
WorkingDirectory=$HERE
ExecStart=$PYTHON $HERE/main.py
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1
Environment=DISPLAY=:0

[Install]
WantedBy=default.target
EOF

chmod 644 "$SERVICE_FILE"

# Disable this service by default to avoid launching the app twice.
# Desktop autostart is the primary startup mechanism.
if command -v systemctl >/dev/null 2>&1; then
    systemctl --user daemon-reload || true

    if systemctl --user is-enabled "$SERVICE_NAME" >/dev/null 2>&1; then
        systemctl --user disable --now "$SERVICE_NAME" || true
    fi

    echo "Created the systemd service but left it disabled."
    echo "Desktop autostart will launch the application instead."
fi

# ------------------------------------------------------------
# 9. Final summary
# ------------------------------------------------------------

echo
echo "============================================================"
echo " Setup completed successfully!"
echo "============================================================"
echo
echo "Project directory:"
echo "  $HERE"
echo
echo "Python virtual environment:"
echo "  $VENV"
echo
echo "Environment file:"
echo "  $HERE/.env"
echo
echo "Desktop autostart:"
echo "  $AUTOSTART_FILE"
echo
echo "NEXT STEPS:"
echo
echo "1. Edit your environment variables:"
echo "   nano \"$HERE/.env\""
echo
echo "2. Check your backend API URL and device/classroom IDs."
echo
echo "3. Test the application:"
echo "   \"$PYTHON\" \"$HERE/main.py\""
echo
echo "4. Reboot to test desktop autostart:"
echo "   sudo reboot"
echo
echo "To install updated Python dependencies later:"
echo "   \"$PIP\" install -r \"$HERE/requirements.txt\""
echo
echo "============================================================"
