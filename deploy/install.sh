#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$HOME/horde-fleet-dashboard"

echo "Creating virtualenv..."
python3 -m venv "$REPO_DIR/.venv"

echo "Installing dependencies..."
"$REPO_DIR/.venv/bin/pip" install -r "$REPO_DIR/requirements.txt"

echo "Installing supervisord config..."
mkdir -p "$HOME/.config/supervisor/conf.d"
mkdir -p "$HOME/.config/supervisor/logs"
cp "$(dirname "$0")/fleet-dashboard.conf" "$HOME/.config/supervisor/conf.d/"

echo "Reloading supervisord..."
supervisorctl reread && supervisorctl update

echo "Checking service status..."
supervisorctl status fleet-dashboard
