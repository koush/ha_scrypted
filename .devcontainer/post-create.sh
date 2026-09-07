#!/bin/bash
set -e

WORKSPACE_DIR=${WORKSPACE_DIR:-$(cd "$(dirname "$0")/.." && pwd)}
CONFIG_DIR="$WORKSPACE_DIR/config"
cd "$WORKSPACE_DIR"

# Install development dependencies
pip install -r requirements_dev.txt

# Install pre-commit hooks
pre-commit install

# Create the Home Assistant config directory with the default configuration
mkdir -p "$CONFIG_DIR"
cp .devcontainer/configuration.yaml "$CONFIG_DIR/configuration.yaml"

# Symlink custom_components into the HA config directory (-n replaces an
# existing symlink instead of creating a nested link inside it)
ln -sfn "$WORKSPACE_DIR/custom_components" "$CONFIG_DIR/custom_components"

echo "Development environment ready!"
