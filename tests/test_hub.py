"""Tests for ScryptedClient."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.helpers.dispatcher import async_dispatcher_connect

from custom_components.scrypted import hub as hub_module
from custom_components.scrypted.const import (
    DOMAIN,
    SIGNAL_DETECTIONS,
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


async def test_detection_subscription_is_shared(hass, entry, fake_sdk):
    """Subscribers share one listenDevice, removed with the last release."""
    client = ScryptedClient(hass, entry)
    await client.async_connect()
    manager = fake_sdk.systemManager
    key = ("cam1", "ObjectDetector")

    payloads = []
    async_dispatcher_connect(
        hass, SIGNAL_DETECTIONS.format(entry.entry_id, "cam1"), payloads.append
    )
    with patch.object(manager, "listenDevice", wraps=manager.listenDevice) as listen:
        release_first = client.async_subscribe_detections("cam1")
        release_second = client.async_subscribe_detections("cam1")
    assert listen.call_count == 1

    manager.fire_device_event("cam1", "ObjectDetector", {"detections": []})
    manager.fire_device_event("cam1", "ObjectDetector", None)
    await hass.async_block_till_done()
    assert payloads == [{"detections": []}, {}]

    release_first()
    assert key in manager.device_listeners
    release_second()
    assert key not in manager.device_listeners
    await client.async_disconnect()


async def test_reconnect_renews_held_detection_subscriptions(
    hass, entry, fake_sdk, mock_connect_sdk
):
    """A reconnect re-registers held subscriptions and drops the dead ones untouched."""
    client = ScryptedClient(hass, entry)
    await client.async_connect()
    manager = fake_sdk.systemManager
    key = ("cam1", "ObjectDetector")
    release = client.async_subscribe_detections("cam1")
    stale = client._detection_registers["cam1"]

    with patch.object(hub_module, "RECONNECT_INITIAL_DELAY", 3600):
        mock_connect_sdk.transport.handlers["disconnect"]()
    # The server-side listener went with the transport.
    manager.device_listeners.clear()

    with patch.object(stale, "removeListener") as remove_stale:
        await client.async_connect()
    remove_stale.assert_not_called()
    assert key in manager.device_listeners

    release()
    assert key not in manager.device_listeners
    await client.async_disconnect()


async def test_detection_subscription_waits_for_sdk(hass, entry, fake_sdk):
    """Subscribing while disconnected registers once the client connects."""
    client = ScryptedClient(hass, entry)
    release = client.async_subscribe_detections("cam1")
    assert fake_sdk.systemManager.device_listeners == {}

    await client.async_connect()
    assert ("cam1", "ObjectDetector") in fake_sdk.systemManager.device_listeners
    release()
    await client.async_disconnect()
