"""Manual end-to-end check of the engine.io client against a real server.

Usage:
    SCRYPTED_HOST=192.168.1.5:10443 SCRYPTED_USERNAME=u SCRYPTED_PASSWORD=p \
        ./venv/bin/python scripts/dev_connect.py
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "vendor" / "scrypted_client")
)


async def main():
    from unittest.mock import MagicMock

    import aiohttp

    from custom_components.scrypted import rpc_transport

    # Minimal HomeAssistant stand-in for async_connect_sdk.
    hass = MagicMock()
    hass.loop = asyncio.get_running_loop()
    session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False))
    rpc_transport.async_get_clientsession = lambda *_, **__: session

    transport, sdk = await rpc_transport.async_connect_sdk(
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
