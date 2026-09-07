"""Tests for scrypted binary sensors."""

from types import SimpleNamespace

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.helpers.dispatcher import async_dispatcher_send

from custom_components.scrypted.binary_sensor import (
    BINARY_SENSORS,
    ScryptedBinarySensor,
)
from custom_components.scrypted.const import (
    DOMAIN,
    SIGNAL_NEW_DEVICE,
)
from tests.conftest import setup_entry


async def test_motion_sensor_created_and_updates(
    hass, fake_sdk, enable_custom_integrations
):
    """Motion sensor created and updates."""
    await setup_entry(hass)

    state = hass.states.get("binary_sensor.porch_front_door_cam_motion")
    assert state is not None
    assert state.state == "off"

    fake_sdk.systemManager.set_property("cam1", "motionDetected", True)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.porch_front_door_cam_motion").state == "on"


async def test_flood_sensor_created(hass, fake_sdk, enable_custom_integrations):
    """Flood sensor created."""
    await setup_entry(hass)
    state = hass.states.get("binary_sensor.basement_basement_leak_flooded")
    assert state is not None
    assert state.state == "off"


async def test_excluded_plugin_has_no_entities(
    hass, fake_sdk, enable_custom_integrations
):
    """Excluded plugin has no entities."""
    await setup_entry(hass)
    # plugin1 (type API) must not create a connectivity sensor
    assert not [
        s
        for s in hass.states.async_all("binary_sensor")
        if "some_plugin" in s.entity_id
    ]


async def test_new_device_added_at_runtime(hass, fake_sdk, enable_custom_integrations):
    """New device added at runtime."""
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
    """Offline device unavailable."""
    await setup_entry(hass)
    fake_sdk.systemManager.set_property("cam1", "online", False)
    await hass.async_block_till_done()
    assert (
        hass.states.get("binary_sensor.porch_front_door_cam_motion").state
        == "unavailable"
    )


async def test_new_device_signal_dedup(hass, fake_sdk, enable_custom_integrations):
    """Re-announcing a known or unknown device creates no duplicate entities."""
    entry = await setup_entry(hass)
    before = len(hass.states.async_all())
    async_dispatcher_send(hass, SIGNAL_NEW_DEVICE.format(entry.entry_id), "cam1")
    async_dispatcher_send(hass, SIGNAL_NEW_DEVICE.format(entry.entry_id), "bell1")
    async_dispatcher_send(hass, SIGNAL_NEW_DEVICE.format(entry.entry_id), "ghost")
    await hass.async_block_till_done()
    assert len(hass.states.async_all()) == before


def test_binary_sensor_is_on_none_when_property_missing(fake_sdk):
    """Return None instead of a bool when the device property is unset."""
    client = SimpleNamespace(sdk=fake_sdk, connected=True)
    entry = MockConfigEntry(domain=DOMAIN)
    description = next(d for d in BINARY_SENSORS if d.key == "motion")
    entity = ScryptedBinarySensor(client, entry, "cam1", description)
    fake_sdk.systemManager.systemState["cam1"].pop("motionDetected")
    assert entity.is_on is None
