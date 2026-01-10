#!/bin/bash

# ==========================================
# Socat Web Manager - Installer & Manager
# ==========================================

REPO_URL="https://github.com/pavlnik/socat-web.git"
INSTALL_DIR="/opt/socat-web-manager"
SERVICE_NAME="socat-web"
DEFAULT_PORT=5000

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check root
if [ "$EUID" -ne 0 ]; then 
  echo -e "${RED}Error: Please run this script as root (sudo ./install.sh)${NC}"
  exit 1
fi

# Helper functions
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
            echo -e "${YELLOW}Warning: Unknown OS. Attempting to install git/python3/socat generically...${NC}"
            ;;
    esac
}

stop_service() {
    if systemctl is-active --quiet $SERVICE_NAME; then
        echo -e "${YELLOW}>>> Stopping service...${NC}"
        systemctl stop $SERVICE_NAME
    fi
}

get_current_port() {
    if [ -f /etc/systemd/system/$SERVICE_NAME.service ]; then
        grep "Environment=\"PORT=" /etc/systemd/system/$SERVICE_NAME.service | cut -d'=' -f3 | tr -d '"'
    else
        echo "$DEFAULT_PORT"
    fi
}

# --- ACTIONS ---

do_install() {
    echo -e "\n${GREEN}=== Install / Update ===${NC}"
    
    # 1. Ask for Port
    CURRENT_PORT=$(get_current_port)
    read -p "Enter port for Web Interface [Default: $CURRENT_PORT]: " WEB_PORT
    WEB_PORT=${WEB_PORT:-$CURRENT_PORT}
    
    install_dependencies

    # 2. Prepare Directory
    if [ ! -d "$INSTALL_DIR" ]; then
        echo -e "${YELLOW}>>> Cloning repository...${NC}"
        git clone "$REPO_URL" "$INSTALL_DIR"
    else
        echo -e "${YELLOW}>>> Updating repository...${NC}"
        cd "$INSTALL_DIR"
        git reset --hard
        git pull
    fi

    # 3. Create Data Directory
    mkdir -p "$INSTALL_DIR/data"
    # Ensure permissions for data
    chmod 755 "$INSTALL_DIR/data"

    # 4. Fix line endings
    echo -e "${YELLOW}>>> Fixing line endings...${NC}"
    find "$INSTALL_DIR" -type f -name "*.py" -exec dos2unix {} +
    find "$INSTALL_DIR" -type f -name "*.sh" -exec dos2unix {} +

    # 5. Python Environment
    echo -e "${YELLOW}>>> Setting up Python environment...${NC}"
    cd "$INSTALL_DIR/backend" || exit
    if [ ! -d "venv" ]; then python3 -m venv venv; fi
    source venv/bin/activate
    pip install --upgrade pip
    pip install Flask werkzeug

    # 6. Service Config
    echo -e "${YELLOW}>>> Configuring Systemd...${NC}"
    SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME.service"

    cat > $SERVICE_FILE <<EOF
[Unit]
Description=Socat Web Manager Interface
After=network.target

[Service]
User=root
WorkingDirectory=$INSTALL_DIR/backend
Environment="PORT=$WEB_PORT"
ExecStart=$INSTALL_DIR/backend/venv/bin/python $INSTALL_DIR/backend/app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable $SERVICE_NAME
    systemctl restart $SERVICE_NAME

    SERVER_IP=$(hostname -I | awk '{print $1}')
    echo -e "\n${GREEN}Success! Application is running.${NC}"
    echo -e "URL: http://$SERVER_IP:$WEB_PORT"
    echo -e "Default Password: admin"
}

do_change_port() {
    if [ ! -f /etc/systemd/system/$SERVICE_NAME.service ]; then
        echo -e "${RED}Error: Service not installed.${NC}"
        return
    fi
    
    CURRENT_PORT=$(get_current_port)
    echo -e "\n${GREEN}=== Change Port ===${NC}"
    read -p "Enter new port [Current: $CURRENT_PORT]: " NEW_PORT
    
    if [[ ! "$NEW_PORT" =~ ^[0-9]+$ ]]; then
        echo -e "${RED}Invalid port.${NC}"
        return
    fi

    # Update systemd file using sed
    sed -i "s/Environment=\"FLASK_PORT=[0-9]*\"/Environment=\"PORT=$NEW_PORT\"/" /etc/systemd/system/$SERVICE_NAME.service
    
    systemctl daemon-reload
    systemctl restart $SERVICE_NAME
    
    echo -e "${GREEN}Port changed to $NEW_PORT. Service restarted.${NC}"
}

do_uninstall() {
    echo -e "\n${RED}=== Uninstall ===${NC}"
    read -p "Are you sure you want to remove Socat Web Manager? (y/N): " CONFIRM
    if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
        echo "Cancelled."
        return
    fi

    stop_service
    systemctl disable $SERVICE_NAME
    rm /etc/systemd/system/$SERVICE_NAME.service
    systemctl daemon-reload
    
    echo -e "${YELLOW}>>> Removing files...${NC}"
    # Ask about data
    read -p "Remove database and settings? (y/N): " RM_DATA
    if [[ "$RM_DATA" == "y" || "$RM_DATA" == "Y" ]]; then
        rm -rf "$INSTALL_DIR"
        echo "Full cleanup completed."
    else
        # Remove code but keep data
        find "$INSTALL_DIR" -mindepth 1 -maxdepth 1 ! -name "data" -exec rm -rf {} +
        echo "App removed. Data kept in $INSTALL_DIR/data"
    fi
}

# --- MAIN MENU ---

show_menu() {
    clear
    echo "========================================="
    echo "   Socat Web - Setup"
    echo "========================================="
    echo "1. Install / Update"
    echo "2. Change Port"
    echo "3. Uninstall"
    echo "4. Exit"
    echo "========================================="
    read -p "Choose an option: " OPTION

    case $OPTION in
        1) do_install ;;
        2) do_change_port ;;
        3) do_uninstall ;;
        4) exit 0 ;;
        *) echo "Invalid option"; sleep 1; show_menu ;;
    esac
}

# Run menu
show_menu
