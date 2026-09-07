"""Tests for ScryptedClient."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.helpers.dispatcher import async_dispatcher_connect

from custom_components.scrypted import hub as hub_module
from custom_components.scrypted.const import (
    DOMAIN,
    SIGNAL_DEVICE_UPDATE,
    SIGNAL_NEW_DEVICE,
)
from custom_components.scrypted.hub import ScryptedClient


@pytest.fixture
def entry(hass):
    """Return a minimal scrypted config entry registered with hass."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": "1.2.3.4", "username": "u", "password": "p"},
    )
    entry.add_to_hass(hass)
    return entry


async def test_connect_populates_devices(hass, entry, fake_sdk):
    """Connect populates devices."""
    client = ScryptedClient(hass, entry)
    await client.async_connect()
    assert client.connected
    assert "cam1" in client.device_ids
    await client.async_disconnect()
    assert not client.connected


async def test_state_change_dispatches_update(hass, entry, fake_sdk):
    """State change dispatches update."""
    client = ScryptedClient(hass, entry)
    await client.async_connect()

    updates = []
    async_dispatcher_connect(
        hass,
        SIGNAL_DEVICE_UPDATE.format(entry.entry_id, "cam1"),
        lambda details, value: updates.append((details["property"], value)),
    )
    fake_sdk.systemManager.set_property("cam1", "motionDetected", True)
    await hass.async_block_till_done()
    assert updates == [("motionDetected", True)]
    await client.async_disconnect()


async def test_unknown_device_dispatches_new_device(hass, entry, fake_sdk):
    """Unknown device dispatches new device."""
    client = ScryptedClient(hass, entry)
    await client.async_connect()

    new = []
    async_dispatcher_connect(
        hass,
        SIGNAL_NEW_DEVICE.format(entry.entry_id),
        new.append,
    )
    fake_sdk.systemManager.systemState["new1"] = {
        "name": {"value": "New Device"},
        "type": {"value": "Sensor"},
        "interfaces": {"value": ["FloodSensor"]},
    }
    fake_sdk.systemManager.set_property("new1", "flooded", False)
    await hass.async_block_till_done()
    assert new == ["new1"]
    await client.async_disconnect()


async def test_disconnect_triggers_reconnect(hass, entry, fake_sdk, mock_connect_sdk):
    """A dropped connection reconnects with backoff after a failed attempt."""
    with patch.object(hub_module, "RECONNECT_INITIAL_DELAY", 0):
        client = ScryptedClient(hass, entry)
        await client.async_connect()

        flaky_state = {"calls": 0}
        real_connect = hub_module.async_connect_sdk

        async def flaky(*args, **kwargs):
            flaky_state["calls"] += 1
            if flaky_state["calls"] == 1:
                raise hub_module.ScryptedConnectionError("boom")
            return await real_connect(*args, **kwargs)

        with patch.object(hub_module, "async_connect_sdk", flaky):
            mock_connect_sdk.transport.handlers["disconnect"]()
            assert client.connected is False

            for _ in range(50):
                if client.connected:
                    break
                await asyncio.sleep(0)
                await hass.async_block_till_done()
            assert client.connected
            assert flaky_state["calls"] == 2

    await client.async_disconnect()
    assert client.device_ids == []
    # disconnect handler is a no-op once closing
    mock_connect_sdk.transport.handlers["disconnect"]()
    assert client.connected is False


async def test_reconnect_survives_unexpected_error(hass, entry, fake_sdk):
    """An unexpected reconnect error is logged and retried, not fatal."""
    client = ScryptedClient(hass, entry)
    await client.async_connect()

    attempts = []

    async def _connect():
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("boom")
        client.connected = True

    with (
        patch.object(client, "async_connect", _connect),
        patch("custom_components.scrypted.hub.asyncio.sleep", AsyncMock()),
    ):
        client.connected = False
        await client._reconnect_loop()

    assert len(attempts) == 2
