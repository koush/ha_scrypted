#!/bin/bash

# Load optional environment overrides
if [ -f /workspaces/ha_scrypted/.devcontainer/.env ]; then
  set -a
  # shellcheck disable=SC1091
  source /workspaces/ha_scrypted/.devcontainer/.env
  set +a
fi

# Start Home Assistant in the background with optional debugpy wait
# Set ENV_DEBUGPY_WAIT=true (via .devcontainer/.env) to pause until a debugger attaches
DEBUGPY_WAIT=${ENV_DEBUGPY_WAIT:-false}
if [ "$DEBUGPY_WAIT" = "true" ]; then
  export SCRYPTED_DEBUGPY_WAIT=true
  echo "================ DEBUGPY ================="
  echo "Starting Home Assistant (debugpy wait ENABLED)."
  echo "Set ENV_DEBUGPY_WAIT=false in .devcontainer/.env or remove the file to disable wait."
  echo "=========================================="
else
  unset SCRYPTED_DEBUGPY_WAIT
  echo "================ DEBUGPY ================="
  echo "Starting Home Assistant (debugpy wait disabled)."
  echo "Set ENV_DEBUGPY_WAIT=true in .devcontainer/.env to pause for debugger attach."
  echo "=========================================="
fi

# Access at http://localhost:8123
echo "Access Home Assistant at http://localhost:8123"
hass -c /config &
