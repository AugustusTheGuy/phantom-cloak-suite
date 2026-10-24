#!/bin/bash
# Delphi Anti-Detection — One-Command VPS Bootstrap (v2 - Enhanced)
set -e

echo "=== Delphi Anti-Detection Server Bootstrap ==="
read -p "Target location (dubai/singapore/vancouver/etc): " LOC
read -p "This server's public IP or hostname: " SERVER_IP

echo "Installing sing-box and hardening..."
apt update && apt install -y curl ufw fail2ban
bash <(curl -fsSL https://sing-box.sagernet.org/deb-install.sh) || true

echo "Applying basic firewall..."
ufw allow 22/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw --force enable

echo "Copy your chosen template from the Mac (example):"
echo "  scp server/ready-for-vps/sing-box-${LOC}-reality.json user@${SERVER_IP}:/tmp/config.json"
echo "  ssh user@${SERVER_IP} 'sudo cp /tmp/config.json /etc/sing-box/config.json && sudo systemctl restart sing-box'"
echo ""
echo "Then on VPS edit the config (UUID, private_key, short_id - generate with: sing-box generate reality-keypair) and:"
echo "  systemctl enable --now sing-box"
echo "  ufw allow 443/tcp"
echo "  ufw allow 443/udp"
echo ""
echo "For batch deploy prep for all top countries, the ready-for-vps/ folder has all templates ready to scp."
echo "Bootstrap complete. See docs/HOWTO_DEPLOY_AND_VERIFY.md for full details."