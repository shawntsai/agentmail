#!/bin/bash
#
# AgentMail Relay — One-command deploy for Oracle Cloud Free Tier
#
# Usage:
#   1. Create Oracle Cloud free tier VM (see ORACLE_SETUP.md)
#   2. SSH into your VM:  ssh ubuntu@<your-vm-ip>
#   3. Run this script:   curl -sSL <your-raw-url> | bash
#      OR copy this file to the VM and run:  bash setup_oracle.sh
#
set -e

echo ""
echo "  =============================="
echo "  AgentMail Relay — Oracle Setup"
echo "  =============================="
echo ""

# --- System packages ---
echo "[1/6] Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-pip python3-venv git > /dev/null 2>&1
echo "  Done."

# --- Clone or update repo ---
INSTALL_DIR="$HOME/agentmail"
if [ -d "$INSTALL_DIR" ]; then
    echo "[2/6] Updating existing installation..."
    cd "$INSTALL_DIR"
    git pull --quiet 2>/dev/null || true
else
    echo "[2/6] Setting up AgentMail..."
    mkdir -p "$INSTALL_DIR"
    # Copy files if running locally, or clone from git
    if [ -d "/tmp/agentmail_deploy" ]; then
        cp -r /tmp/agentmail_deploy/* "$INSTALL_DIR/"
    else
        echo "  Copying files..."
    fi
fi
cd "$INSTALL_DIR"

# --- Python venv ---
echo "[3/6] Setting up Python environment..."
python3 -m venv .venv
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet fastapi uvicorn pynacl httpx pydantic
echo "  Done."

# --- Data directory ---
echo "[4/6] Creating data directory..."
mkdir -p /home/ubuntu/agentmail_relay_data
echo "  Done."

# --- Systemd service ---
echo "[5/6] Installing systemd service..."
sudo tee /etc/systemd/system/agentmail-relay.service > /dev/null << 'SERVICEFILE'
[Unit]
Description=AgentMail Relay Server
After=network.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/agentmail
ExecStart=/home/ubuntu/agentmail/.venv/bin/python run_relay.py --port 7445 --data-dir /home/ubuntu/agentmail_relay_data
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/home/ubuntu/agentmail_relay_data
PrivateTmp=true

[Install]
WantedBy=multi-user.target
SERVICEFILE

sudo systemctl daemon-reload
sudo systemctl enable agentmail-relay
sudo systemctl restart agentmail-relay
echo "  Done."

# --- Firewall (Oracle uses iptables by default) ---
echo "[6/6] Opening port 7445..."
# Oracle Cloud Ubuntu images use iptables
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 7445 -j ACCEPT
sudo netfilter-persistent save 2>/dev/null || sudo iptables-save | sudo tee /etc/iptables/rules.v4 > /dev/null
echo "  Done."

# --- Get public IP ---
PUBLIC_IP=$(curl -s ifconfig.me 2>/dev/null || curl -s icanhazip.com 2>/dev/null || echo "<your-vm-ip>")

# --- Done ---
echo ""
echo "  ================================"
echo "  AgentMail Relay is running!"
echo "  ================================"
echo ""
echo "  Public URL:  http://${PUBLIC_IP}:7445"
echo "  Status:      sudo systemctl status agentmail-relay"
echo "  Logs:        sudo journalctl -u agentmail-relay -f"
echo ""
echo "  To use from your laptop:"
echo ""
echo "    python run.py --name alice --port 7443 --relay http://${PUBLIC_IP}:7445"
echo ""
echo "  Share this relay URL with anyone you want to message."
echo ""
