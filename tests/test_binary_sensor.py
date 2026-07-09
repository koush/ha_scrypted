"""Tests for scrypted binary sensors."""
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.scrypted.const import (
    CONF_AUTO_REGISTER_RESOURCES,
    CONF_DEVICE_TYPES,
    CONF_ENABLE_ENTITIES,
    CONF_SCRYPTED_NVR,
    DOMAIN,
)


async def setup_entry(hass, device_types=None):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "host": "1.2.3.4",
            "username": "u",
            "password": "p",
            "name": "Scrypted",
            "icon": "mdi:memory",
        },
        options={
            CONF_AUTO_REGISTER_RESOURCES: False,
            CONF_SCRYPTED_NVR: False,
            CONF_ENABLE_ENTITIES: True,
            CONF_DEVICE_TYPES: device_types or ["Camera", "Doorbell", "Sensor"],
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_motion_sensor_created_and_updates(
    hass, fake_sdk, enable_custom_integrations
):
    await setup_entry(hass)

    state = hass.states.get("binary_sensor.front_door_cam_motion")
    assert state is not None
    assert state.state == "off"

    fake_sdk.systemManager.set_property("cam1", "motionDetected", True)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.front_door_cam_motion").state == "on"


async def test_flood_sensor_created(hass, fake_sdk, enable_custom_integrations):
    await setup_entry(hass)
    state = hass.states.get("binary_sensor.basement_leak_flooded")
    assert state is not None
    assert state.state == "off"


async def test_excluded_plugin_has_no_entities(
    hass, fake_sdk, enable_custom_integrations
):
    await setup_entry(hass)
    # plugin1 (type API) must not create a connectivity sensor
    assert not [
        s
        for s in hass.states.async_all("binary_sensor")
        if "some_plugin" in s.entity_id
    ]


async def test_new_device_added_at_runtime(hass, fake_sdk, enable_custom_integrations):
    await setup_entry(hass)
    fake_sdk.systemManager.systemState["new1"] = {
        "name": {"value": "Garage Leak"},
        "type": {"value": "Sensor"},
        "info": {"value": {}},
        "interfaces": {"value": ["FloodSensor"]},
    }
    fake_sdk.systemManager.set_property("new1", "flooded", True)
    await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.garage_leak_flooded")
    assert state is not None
    assert state.state == "on"


async def test_offline_device_unavailable(hass, fake_sdk, enable_custom_integrations):
    await setup_entry(hass)
    fake_sdk.systemManager.set_property("cam1", "online", False)
    await hass.async_block_till_done()
    assert (
        hass.states.get("binary_sensor.front_door_cam_motion").state == "unavailable"
    )


async def test_new_device_signal_dedup(hass, fake_sdk, enable_custom_integrations):
    """Re-announcing a known or unknown device creates no duplicate entities."""
    from homeassistant.helpers.dispatcher import async_dispatcher_send

    from custom_components.scrypted.const import SIGNAL_NEW_DEVICE

    entry = await setup_entry(hass)
    before = len(hass.states.async_all())
    async_dispatcher_send(hass, SIGNAL_NEW_DEVICE.format(entry.entry_id), "cam1")
    async_dispatcher_send(hass, SIGNAL_NEW_DEVICE.format(entry.entry_id), "bell1")
    async_dispatcher_send(hass, SIGNAL_NEW_DEVICE.format(entry.entry_id), "ghost")
    await hass.async_block_till_done()
    assert len(hass.states.async_all()) == before
