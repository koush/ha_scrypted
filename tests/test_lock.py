"""Tests for scrypted locks."""

from homeassistant.helpers.dispatcher import async_dispatcher_send

from custom_components.scrypted.const import SIGNAL_NEW_DEVICE
from tests.conftest import setup_entry

TYPES = ["Camera", "Doorbell", "Lock"]


async def test_lock_discovered_and_states(hass, fake_sdk, enable_custom_integrations):
    """Lock discovered and states."""
    await setup_entry(hass, device_types=TYPES)
    assert hass.states.get("lock.side_door").state == "locked"

    fake_sdk.systemManager.set_property("lock1", "lockState", "Unlocked")
    await hass.async_block_till_done()
    assert hass.states.get("lock.side_door").state == "unlocked"

    fake_sdk.systemManager.set_property("lock1", "lockState", "Jammed")
    await hass.async_block_till_done()
    assert hass.states.get("lock.side_door").state == "jammed"


async def test_lock_not_in_allowlist_skipped(
    hass, fake_sdk, enable_custom_integrations
):
    """Lock device present but excluded from the configured type allowlist."""
    await setup_entry(hass, device_types=["Camera", "Doorbell"])
    assert hass.states.get("lock.side_door") is None


async def test_lock_commands(hass, fake_sdk, enable_custom_integrations):
    """Lock commands."""
    await setup_entry(hass, device_types=TYPES)
    device = fake_sdk.systemManager.getDeviceById("lock1")

    await hass.services.async_call(
        "lock", "unlock", {"entity_id": "lock.side_door"}, blocking=True
    )
    device.unlock.assert_awaited_once()

    await hass.services.async_call(
        "lock", "lock", {"entity_id": "lock.side_door"}, blocking=True
    )
    device.lock.assert_awaited_once()


async def test_new_device_signal_ignored_for_unknown_or_disconnected(
    hass, fake_sdk, enable_custom_integrations
):
    """New device signal ignored for unknown or disconnected."""
    entry = await setup_entry(hass, device_types=TYPES)
    before = len(hass.states.async_entity_ids("lock"))

    # unknown device id: getDeviceById returns None
    async_dispatcher_send(hass, SIGNAL_NEW_DEVICE.format(entry.entry_id), "nope")
    await hass.async_block_till_done()
    assert len(hass.states.async_entity_ids("lock")) == before

    # SDK dropped (disconnected) while a new-device signal arrives
    entry.runtime_data.client.sdk = None
    async_dispatcher_send(hass, SIGNAL_NEW_DEVICE.format(entry.entry_id), "lock1")
    await hass.async_block_till_done()
    assert len(hass.states.async_entity_ids("lock")) == before
