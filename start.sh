#!/bin/bash
set -e

ENV_FILE="$(dirname "$0")/.env"

# Load existing .env if present
if [ -f "$ENV_FILE" ]; then
    # shellcheck disable=SC1090
    source "$ENV_FILE"
fi

# Prompt for HOST_IP if not already set
if [ -z "$HOST_IP" ]; then
    echo "Pathway needs to know your host's LAN IP to generate correct container URLs."
    echo "This is the IP address your browser uses to reach this machine."
    echo ""
    read -rp "Enter HOST_IP (e.g. 192.168.1.100): " HOST_IP

    if [ -z "$HOST_IP" ]; then
        echo "Error: HOST_IP cannot be empty." >&2
        exit 1
    fi

    # Persist to .env so subsequent docker compose commands work
    echo "HOST_IP=$HOST_IP" >> "$ENV_FILE"
    echo "Saved to .env"
fi

docker compose up -d
