#!/bin/bash
# Delphi Anti-Detection - Deploy all server templates to ready VPSes
# Usage: edit the VPS_IPS associative array with your actual VPS IPs/hostnames, then run ./deploy_all.sh
# This will scp the templates and print next steps.

declare -A VPS_IPS=(
  ["vancouver"]="user@your-vancouver-vps-ip"
  ["dubai"]="user@your-dubai-vps-ip"
  ["singapore"]="user@your-singapore-vps-ip"
  ["hongkong"]="user@your-hongkong-vps-ip"
  ["germany"]="user@your-germany-vps-ip"
  ["bahamas"]="user@your-bahamas-vps-ip"
  ["cayman"]="user@your-cayman-vps-ip"
  ["mauritius"]="user@your-mauritius-vps-ip"
  # add seychelles etc. as needed
)

for loc in "${!VPS_IPS[@]}"; do
  ip=${VPS_IPS[$loc]}
  template="ready-for-vps/sing-box-${loc}-reality.json"
  if [ -f "$template" ]; then
    echo "Deploying $loc to $ip..."
    scp "$template" "$ip:/tmp/config.json"
    echo "On $ip, run: sudo cp /tmp/config.json /etc/sing-box/config.json && sudo systemctl restart sing-box"
    echo "Then edit config with real keys, open ports, etc."
  else
    echo "No template for $loc"
  fi
done

echo "All deploys scripted. Edit this file with real IPs and run it."
