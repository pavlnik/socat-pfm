#!/bin/bash

# Check root permissions
if [ "$EUID" -ne 0 ]; then 
  echo "Error: Please run this script as root (sudo ./install.sh)"
  exit 1
fi

# --- CONFIGURATION & PATHS ---
SOURCE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
TARGET_DIR="/opt/socat-web"
DB_FILE="$TARGET_DIR/backend/socat.db"
BACKUP_DB="/tmp/socat.db.backup"
DEFAULT_PORT=5000

# --- INTERACTIVE SETUP ---
echo "========================================="
echo "   Socat Web Manager Installation"
echo "========================================="

read -p "Enter port for Web Interface [Default: $DEFAULT_PORT]: " WEB_PORT
WEB_PORT=${WEB_PORT:-$DEFAULT_PORT}

if ! [[ "$WEB_PORT" =~ ^[0-9]+$ ]] || [ "$WEB_PORT" -lt 1 ] || [ "$WEB_PORT" -gt 65535 ]; then
    echo "Error: Invalid port number. Using default $DEFAULT_PORT."
    WEB_PORT=$DEFAULT_PORT
fi

echo ">>> Selected Port: $WEB_PORT"

# --- DETECT OS & INSTALL DEPENDENCIES ---
echo ">>> Detecting OS..."
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
else
    echo "Error: Cannot detect OS. /etc/os-release not found."
    exit 1
fi

echo ">>> Installing system dependencies for $OS..."

case $OS in
    ubuntu|debian|kali)
        apt-get update
        apt-get install -y python3 python3-pip python3-venv socat dos2unix
        ;;
    centos|rhel)
        yum install -y epel-release
        yum install -y python3 python3-pip socat dos2unix
        ;;
    fedora)
        dnf install -y python3 python3-pip socat dos2unix
        ;;
    *)
        echo "Warning: Unsupported OS '$OS'. Attempting to continue, assuming python3 and socat are installed..."
        ;;
esac

# --- BACKUP & CLEANUP ---
if systemctl is-active --quiet socat-web; then
    echo ">>> Stopping existing service..."
    systemctl stop socat-web
fi

if [ -f "$DB_FILE" ]; then
    echo ">>> Backing up database..."
    cp "$DB_FILE" "$BACKUP_DB"
fi

if [ -d "$TARGET_DIR" ]; then
    echo ">>> Cleaning up old files..."
    rm -rf "$TARGET_DIR"
fi

# --- COPY FILES ---
echo ">>> Copying application files..."
mkdir -p "$TARGET_DIR"
cp -r "$SOURCE_DIR/backend" "$TARGET_DIR/"
cp -r "$SOURCE_DIR/frontend" "$TARGET_DIR/"
cp "$SOURCE_DIR/README.md" "$TARGET_DIR/"

# Restore Database
if [ -f "$BACKUP_DB" ]; then
    echo ">>> Restoring database..."
    cp "$BACKUP_DB" "$DB_FILE"
    rm "$BACKUP_DB"
    # Fix permissions just in case
    chmod 664 "$DB_FILE"
fi

# Fix line endings
echo ">>> Converting line endings..."
find "$TARGET_DIR" -type f -name "*.py" -exec dos2unix {} +

# --- PYTHON ENVIRONMENT ---
echo ">>> Setting up Python virtual environment..."
cd "$TARGET_DIR/backend" || exit
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
# Installing only required packages (No six, No pam)
pip install Flask werkzeug

# --- SERVICE CONFIGURATION ---
echo ">>> Configuring Systemd service..."
SERVICE_FILE="/etc/systemd/system/socat-web.service"

cat > $SERVICE_FILE <<EOF
[Unit]
Description=Socat Web Manager Interface
After=network.target

[Service]
User=root
WorkingDirectory=$TARGET_DIR/backend
# Pass the port as an environment variable
Environment="FLASK_PORT=$WEB_PORT"
ExecStart=$TARGET_DIR/backend/venv/bin/python $TARGET_DIR/backend/app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Restart service
systemctl daemon-reload
systemctl enable socat-web
systemctl restart socat-web

# --- FINISH ---
SERVER_IP=$(hostname -I | awk '{print $1}')
echo ""
echo "========================================="
echo "   Installation Complete!"
echo "========================================="
echo "URL: http://$SERVER_IP:$WEB_PORT"
echo "Default Password: admin"
echo "To change port later: Re-run install.sh or edit /etc/systemd/system/socat-web.service"
echo ""