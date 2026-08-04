"""Manual end-to-end check of the engine.io client against a real server.

Usage:
    SCRYPTED_HOST=192.168.1.5:10443 SCRYPTED_USERNAME=u SCRYPTED_PASSWORD=p \
        ./venv/bin/python scripts/dev_connect.py
"""
import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.scrypted import sdk as sdk_module  # noqa: E402


async def main():
    # Minimal HomeAssistant stand-in for async_connect_sdk.
    hass = MagicMock()
    hass.loop = asyncio.get_running_loop()
    session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False))
    sdk_module.async_get_clientsession = lambda *_, **__: session
    sdk_module.async_create_clientsession = lambda *_, **__: aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(ssl=False)
    )

    transport, sdk = await sdk_module.async_connect_sdk(
        hass,
        os.environ["SCRYPTED_HOST"],
        os.environ["SCRYPTED_USERNAME"],
        os.environ["SCRYPTED_PASSWORD"],
    )
    state = sdk.systemManager.getSystemState()
    print(f"Connected. {len(state)} devices:")
    for device_id in state:
        device = sdk.systemManager.getDeviceById(device_id)
        print(
            f"  {device_id}: {device.name} type={device.type} "
            f"interfaces={device.interfaces}"
        )
    await transport.close()
    await session.close()


asyncio.run(main())
