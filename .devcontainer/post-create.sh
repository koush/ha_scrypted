#!/bin/bash
set -e

# Install development dependencies
pip install -r requirements_dev.txt

# Install pre-commit hooks
pre-commit install

# Create config directory if it doesn't exist
mkdir -p /config

# Copy default configuration
cp .devcontainer/configuration.yaml /config/configuration.yaml

# Symlink custom_components to HA config directory
ln -sf /workspaces/ha_scrypted/custom_components /config/custom_components

echo "Development environment ready!"
