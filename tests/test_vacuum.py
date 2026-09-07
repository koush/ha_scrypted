"""Tests for scrypted vacuums."""

from tests.conftest import setup_entry

TYPES = ["Camera", "Doorbell", "Vacuum"]


async def test_vacuum_activity_states(hass, fake_sdk, enable_custom_integrations):
    """Vacuum activity states."""
    await setup_entry(hass, device_types=TYPES)
    assert hass.states.get("vacuum.robo_vac").state == "docked"

    fake_sdk.systemManager.set_property("vac1", "docked", False)
    fake_sdk.systemManager.set_property("vac1", "running", True)
    await hass.async_block_till_done()
    assert hass.states.get("vacuum.robo_vac").state == "cleaning"

    fake_sdk.systemManager.set_property("vac1", "paused", True)
    await hass.async_block_till_done()
    assert hass.states.get("vacuum.robo_vac").state == "paused"

    fake_sdk.systemManager.set_property("vac1", "running", False)
    fake_sdk.systemManager.set_property("vac1", "paused", False)
    await hass.async_block_till_done()
    assert hass.states.get("vacuum.robo_vac").state == "idle"


async def test_vacuum_commands(hass, fake_sdk, enable_custom_integrations):
    """Vacuum commands."""
    await setup_entry(hass, device_types=TYPES)
    device = fake_sdk.systemManager.getDeviceById("vac1")

    await hass.services.async_call(
        "vacuum", "start", {"entity_id": "vacuum.robo_vac"}, blocking=True
    )
    device.start.assert_awaited_once()

    await hass.services.async_call(
        "vacuum", "pause", {"entity_id": "vacuum.robo_vac"}, blocking=True
    )
    device.pause.assert_awaited_once()

    # start while paused resumes
    fake_sdk.systemManager.set_property("vac1", "running", True)
    fake_sdk.systemManager.set_property("vac1", "paused", True)
    await hass.async_block_till_done()
    await hass.services.async_call(
        "vacuum", "start", {"entity_id": "vacuum.robo_vac"}, blocking=True
    )
    device.resume.assert_awaited_once()

    await hass.services.async_call(
        "vacuum", "stop", {"entity_id": "vacuum.robo_vac"}, blocking=True
    )
    device.stop.assert_awaited_once()

    await hass.services.async_call(
        "vacuum", "return_to_base", {"entity_id": "vacuum.robo_vac"}, blocking=True
    )
    device.dock.assert_awaited_once()


async def test_vacuum_activity_none_when_device_gone(
    hass, fake_sdk, enable_custom_integrations
):
    """Vacuum activity none when device gone."""
    entry = await setup_entry(hass, device_types=TYPES)
    entity = hass.data["entity_components"]["vacuum"].get_entity("vacuum.robo_vac")

    entry.runtime_data.client.sdk = None
    try:
        assert entity.activity is None
    finally:
        entry.runtime_data.client.sdk = fake_sdk
