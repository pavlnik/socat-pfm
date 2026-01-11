#!/bin/bash

# ==========================================
# Socat PFM - Installer & Manager
# ==========================================

# Paths and names
REPO_URL="https://github.com/pavlnik/socat-pfm.git"
INSTALL_DIR="/opt/socat-pfm"
SERVICE_NAME="socat-pfm"
DEFAULT_PORT=5000

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Root check
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Error: Please run this script as root (sudo ./install.sh)${NC}"
    exit 1
fi

# --- Helper functions ---

detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$ID
    else
        echo -e "${RED}Error: Cannot detect OS.${NC}"
        exit 1
    fi
}

install_dependencies() {
    detect_os
    echo -e "${YELLOW}>>> Installing system dependencies for $OS...${NC}"

    case $OS in
        ubuntu|debian|kali)
            apt-get update
            apt-get install -y python3 python3-pip python3-venv socat dos2unix git
            ;;
        centos|rhel|fedora)
            if [ "$OS" == "centos" ]; then yum install -y epel-release; fi
            yum install -y python3 python3-pip socat dos2unix git
            ;;
        *)
            echo -e "${YELLOW}Warning: Unknown OS. Trying generic install for git/python3/socat...${NC}"
            apt-get install -y python3 python3-pip python3-venv socat dos2unix git || yum install -y python3 python3-pip socat dos2unix git
            ;;
    esac
}

get_current_port() {
    if [ -f "/etc/systemd/system/$SERVICE_NAME.service" ]; then
        grep "Environment=\"PORT=" "/etc/systemd/system/$SERVICE_NAME.service" | cut -d'=' -f3 | tr -d '"'
    else
        echo "$DEFAULT_PORT"
    fi
}

create_service() {
    local port=$1
    echo -e "${YELLOW}>>> Configuring Systemd service (PORT=$port)...${NC}"

    SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME.service"

    cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Socat PFM Web Manager
After=network.target

[Service]
User=root
WorkingDirectory=$INSTALL_DIR/backend
Environment="PORT=$port"
ExecStart=$INSTALL_DIR/backend/venv/bin/python3 app.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME"
    systemctl restart "$SERVICE_NAME"
    echo -e "${GREEN}Service $SERVICE_NAME is running on port $port!${NC}"
}

# --- Actions ---

do_install() {
    echo -e "\n${GREEN}=== Socat PFM Installation ===${NC}"

    # Ask for port only on first install
    read -p "Enter port for Web UI [Default: $DEFAULT_PORT]: " WEB_PORT
    WEB_PORT=${WEB_PORT:-$DEFAULT_PORT}

    install_dependencies

    # Clone repository
    if [ ! -d "$INSTALL_DIR" ]; then
        echo -e "${YELLOW}>>> Cloning repository...${NC}"
        git clone "$REPO_URL" "$INSTALL_DIR"
    else
        echo -e "${YELLOW}Install directory already exists. Use Update instead.${NC}"
    fi

    # Data directory
    mkdir -p "$INSTALL_DIR/data"
    chmod 755 "$INSTALL_DIR/data"

    # Fix line endings (just in case)
    find "$INSTALL_DIR" -type f -name "*.py" -exec dos2unix {} + 2>/dev/null
    find "$INSTALL_DIR" -type f -name "*.sh" -exec dos2unix {} + 2>/dev/null

    # Python venv
    echo -e "${YELLOW}>>> Setting up Python venv...${NC}"
    cd "$INSTALL_DIR/backend" || exit
    if [ ! -d "venv" ]; then python3 -m venv venv; fi
    source venv/bin/activate
    pip install --upgrade pip
    pip install Flask werkzeug

    # Create & start service
    create_service "$WEB_PORT"

    echo -e "\n${GREEN}Installation complete! Open: http://<YOUR_IP>:$WEB_PORT${NC}"
    read -p "Press Enter to continue..."
}

do_update() {
    echo -e "\n${GREEN}=== Socat PFM Update ===${NC}"

    if [ ! -d "$INSTALL_DIR" ]; then
        echo -e "${RED}Error: Install directory not found. Please install first.${NC}"
        return
    fi

    # Keep current port; do NOT ask
    CURRENT_PORT=$(get_current_port)
    echo -e "${YELLOW}>>> Using current port: $CURRENT_PORT${NC}"

    cd "$INSTALL_DIR" || exit
    echo -e "${YELLOW}>>> Pulling updates from git...${NC}"
    git reset --hard
    git pull

    echo -e "${YELLOW}>>> Updating Python dependencies...${NC}"
    cd "$INSTALL_DIR/backend" || exit
    if [ ! -d "venv" ]; then python3 -m venv venv; fi
    source venv/bin/activate
    pip install --upgrade pip
    pip install Flask werkzeug

    echo -e "${YELLOW}>>> Restarting service...${NC}"
    systemctl restart "$SERVICE_NAME"

    echo -e "${GREEN}Update completed!${NC}"
    read -p "Press Enter to continue..."
}

do_change_port() {
    echo -e "\n${GREEN}=== Change Port ===${NC}"
    CURRENT_PORT=$(get_current_port)
    read -p "Enter new port [Current: $CURRENT_PORT]: " NEW_PORT
    NEW_PORT=${NEW_PORT:-$CURRENT_PORT}

    if [ "$NEW_PORT" == "$CURRENT_PORT" ]; then
        echo "Port unchanged."
    else
        create_service "$NEW_PORT"
    fi
    read -p "Press Enter to continue..."
}

do_uninstall() {
    echo -e "\n${RED}=== Uninstall Socat PFM ===${NC}"
    read -p "Are you sure? (y/N): " CONFIRM
    if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
        echo "Cancelled."
        return
    fi

    echo -e "${YELLOW}>>> Stopping service...${NC}"
    systemctl stop "$SERVICE_NAME" 2>/dev/null
    systemctl disable "$SERVICE_NAME" 2>/dev/null
    rm -f "/etc/systemd/system/$SERVICE_NAME.service"
    systemctl daemon-reload

    read -p "Remove database and settings too? (y/N): " RM_DATA
    if [[ "$RM_DATA" == "y" || "$RM_DATA" == "Y" ]]; then
        rm -rf "$INSTALL_DIR"
        echo "Full removal completed."
    else
        find "$INSTALL_DIR" -mindepth 1 -maxdepth 1 ! -name "data" -exec rm -rf {} +
        echo "App removed. Data kept in $INSTALL_DIR/data"
    fi

    exit 0
}

# --- Menus ---

show_installed_menu() {
    while true; do
        clear
        echo "========================================="
        echo " Socat PFM - Manager"
        echo "========================================="
        echo "1. Update"
        echo "2. Change port"
        echo "3. Uninstall"
        echo "4. Exit"
        echo "========================================="
        read -p "Choose an option: " OPTION
        case $OPTION in
            1) do_update ;;
            2) do_change_port ;;
            3) do_uninstall ;;
            4) exit 0 ;;
            *) echo "Invalid option"; sleep 1 ;;
        esac
    done
}

show_install_menu() {
    while true; do
        clear
        echo "========================================="
        echo " Socat PFM - Setup"
        echo "========================================="
        echo "1. Install"
        echo "2. Exit"
        echo "========================================="
        read -p "Choose an option: " OPTION
        case $OPTION in
            1)
                do_install
                exit 0 
                ;;
            2) exit 0 ;;
            *) echo "Invalid option"; sleep 1 ;;
        esac
    done
}

# --- Entry point ---

if [ -d "$INSTALL_DIR" ]; then
    show_installed_menu
else
    show_install_menu
fi
