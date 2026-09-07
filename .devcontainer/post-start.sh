#!/bin/bash

WORKSPACE_DIR=${WORKSPACE_DIR:-$(cd "$(dirname "$0")/.." && pwd)}
CONFIG_DIR="$WORKSPACE_DIR/config"

# Load optional environment overrides, e.g. ENV_DEBUGPY_WAIT=true to make
# Home Assistant wait for a debugger to attach (see .devcontainer/.env.example)
if [ -f "$WORKSPACE_DIR/.devcontainer/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$WORKSPACE_DIR/.devcontainer/.env"
  set +a
fi

echo "Starting Home Assistant (ENV_DEBUGPY_WAIT=${ENV_DEBUGPY_WAIT:-false})"
echo "Access Home Assistant at http://localhost:8123"
hass -c "$CONFIG_DIR" &
