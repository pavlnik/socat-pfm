# Socat Port Forward Manager (PFM)

A modern, responsive web interface for managing TCP/UDP port forwarding with **Socat**. Perfect for proxying traffic between servers, containers, or networks.

**Features:**
- 🚀 Fast, lightweight Flask backend
- 📱 Fully responsive mobile interface
- 🔒 Password-protected
- 🔄 Dynamic port range support
- 🛡️ Automatic port conflict detection
- 🐳 Docker support
- 📋 Rule descriptions for easy management
- 🎨 Dark theme with real-time status indicators
- 📊 Beautiful Toast notifications

## Installation

### Automatic (Recommended)

```bash
curl -o install.sh https://raw.githubusercontent.com/pavlnik/socat-pfm/main/install.sh && sudo bash install.sh
```

The script handles:
- ✅ OS detection (apt/yum/dnf)
- ✅ Dependency installation
- ✅ Git cloning to `/opt/socat-pfm`
- ✅ Python venv setup
- ✅ Systemd service creation
- ✅ Service auto-start

### Manual

```bash
git clone https://github.com/pavlnik/socat-pfm.git
cd socat-pfm
sudo bash install.sh
```

### Docker

```bash
docker run -d \
  --name socat-pfm \
  --restart always \
  --network host \
  -e FLASK_PORT=5000 \
  -v socat-data:/app/data \
  ghcr.io/pavlnik/socat-pfm:latest
```

**⚠️ Important:** Use `--network host` so Socat can bind to any port on the host. In bridge mode, port forwarding only works inside the container.


## Usage


### Access the app

```
http://<your-server-ip>:5000
```

**Default credentials:**
- Password: `admin` (⚠️ change immediately!)

### Creating a Port Forward Rule

1. Click **"Add Rule"**
2. Fill in:
   - **Inbound IP**: Interface to listen on (default: `0.0.0.0` = all)
   - **Inbound Port(s)**: Port or range (e.g., `8080` or `8000-8005`)
   - **Protocol**: TCP or UDP
   - **Destination IP**: Target server IP
   - **Destination Port(s)**: Target port (range must match inbound count)
   - **Description** (optional): e.g., "Web Server", "Database Proxy"
3. Click **"Save Rule"**
4. Toggle the rule **"Active"** to start forwarding

### Example Rules

**Proxy HTTPS to internal web server:**
```
Inbound: 0.0.0.0:443 (TCP)
Dest: 192.168.1.100:8080
```

**Forward multiple ports:**
```
Inbound: 0.0.0.0:3306-3308 (TCP)
Dest: 10.0.0.5:3306-3308
```

**UDP DNS proxy:**
```
Inbound: 0.0.0.0:53 (UDP)
Dest: 8.8.8.8:53
```

## Configuration

### Change Port After Installation

Use the interactive menu:
```bash
sudo bash install.sh
# Select option 2: Change port
```

Or manually:
```bash
sudo nano /etc/systemd/system/socat-pfm.service
# Edit: Environment="PORT=5000"
sudo systemctl daemon-reload
sudo systemctl restart socat-pfm
```

### Change Password

1. Click **🔒 Password** button in the navbar
2. Enter current and new password
3. Click **"Update"**

### Database Location

```
/opt/socat-pfm/data/socat.db
```

Backup:
```bash
sudo cp /opt/socat-pfm/data/socat.db ~/socat.db.backup
```
