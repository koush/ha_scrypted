"""Tests for scrypted locks."""
from tests.test_binary_sensor import setup_entry

TYPES = ["Camera", "Doorbell", "Lock"]


async def test_lock_discovered_and_states(hass, fake_sdk, enable_custom_integrations):
    await setup_entry(hass, device_types=TYPES)
    assert hass.states.get("lock.side_door").state == "locked"

    fake_sdk.systemManager.set_property("lock1", "lockState", "Unlocked")
    await hass.async_block_till_done()
    assert hass.states.get("lock.side_door").state == "unlocked"

    fake_sdk.systemManager.set_property("lock1", "lockState", "Jammed")
    await hass.async_block_till_done()
    assert hass.states.get("lock.side_door").state == "jammed"


async def test_lock_not_in_allowlist_skipped(hass, fake_sdk, enable_custom_integrations):
    """Lock device present but excluded from the configured type allowlist."""
    await setup_entry(hass, device_types=["Camera", "Doorbell"])
    assert hass.states.get("lock.side_door") is None


async def test_lock_commands(hass, fake_sdk, enable_custom_integrations):
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
