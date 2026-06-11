"""Tests for ScryptedClient."""
import pytest
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.scrypted.client import ScryptedClient
from custom_components.scrypted.const import (
    DOMAIN,
    SIGNAL_DEVICE_UPDATE,
    SIGNAL_NEW_DEVICE,
)


@pytest.fixture
def entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": "1.2.3.4", "username": "u", "password": "p"},
    )
    entry.add_to_hass(hass)
    return entry


async def test_connect_populates_devices(hass, entry, fake_sdk):
    client = ScryptedClient(hass, entry)
    await client.async_connect()
    assert client.connected
    assert "cam1" in client.device_ids
    await client.async_disconnect()
    assert not client.connected


async def test_state_change_dispatches_update(hass, entry, fake_sdk):
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
    client = ScryptedClient(hass, entry)
    await client.async_connect()

    new = []
    async_dispatcher_connect(
        hass,
        SIGNAL_NEW_DEVICE.format(entry.entry_id),
        lambda device_id: new.append(device_id),
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
