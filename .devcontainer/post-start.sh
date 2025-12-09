#!/bin/bash

# Start Home Assistant in the background
# Access at http://localhost:8123
echo "Starting Home Assistant..."
echo "Access Home Assistant at http://localhost:8123"
hass -c /config &
