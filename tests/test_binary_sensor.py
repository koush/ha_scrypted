"""Tests for scrypted binary sensors."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send

from custom_components.scrypted import ScryptedRuntimeData
from custom_components.scrypted.binary_sensor import (
    BINARY_SENSORS,
    DETECTION_TIMEOUT,
    ScryptedBinarySensor,
    ScryptedObjectDetectedSensor,
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
    entry.runtime_data = ScryptedRuntimeData(
        token="token", client=client, hub_device_id="hub"
    )
    entity = ScryptedBinarySensor(client, entry, "cam1", description)
    fake_sdk.systemManager.systemState["cam1"].pop("motionDetected")
    assert entity.is_on is None


async def test_online_sensor_reports_off_when_device_offline(
    hass, fake_sdk, enable_custom_integrations
):
    """The connectivity sensor reports off rather than going unavailable."""
    await setup_entry(hass)
    online = "binary_sensor.porch_front_door_cam_online"
    assert hass.states.get(online).state == "on"

    fake_sdk.systemManager.set_property("cam1", "online", False)
    await hass.async_block_till_done()

    # The sensor that reports the online property stays available and says off,
    # while every other entity on the device goes unavailable.
    assert hass.states.get(online).state == "off"
    assert (
        hass.states.get("binary_sensor.porch_front_door_cam_motion").state
        == "unavailable"
    )


PERSON_DETECTED = "binary_sensor.porch_front_door_cam_person_detected"
CAR_DETECTED = "binary_sensor.porch_front_door_cam_car_detected"


def _detect(fake_sdk, *class_names: str) -> None:
    fake_sdk.systemManager.fire_device_event(
        "cam1",
        "ObjectDetector",
        {"detections": [{"className": name, "score": 0.9} for name in class_names]},
    )


async def _setup_with_detected_sensors_enabled(hass: HomeAssistant):
    with patch.object(
        ScryptedObjectDetectedSensor, "_attr_entity_registry_enabled_default", True
    ):
        return await setup_entry(hass)


async def test_detected_sensors_created_disabled(
    hass, fake_sdk, enable_custom_integrations
):
    """Each advertised class gets a sensor, created disabled."""
    await setup_entry(hass)
    registry = er.async_get(hass)

    for entity_id in (PERSON_DETECTED, CAR_DETECTED):
        entity = registry.async_get(entity_id)
        assert entity is not None
        assert entity.disabled_by is er.RegistryEntryDisabler.INTEGRATION
        assert hass.states.get(entity_id) is None
    # bell1 has no ObjectDetector interface
    assert not [
        entity_id
        for entity_id in registry.entities
        if entity_id.startswith("binary_sensor.doorbell_") and "detected" in entity_id
    ]


async def test_detected_sensor_turns_off_after_quiet_period(
    hass, fake_sdk, enable_custom_integrations, freezer: FrozenDateTimeFactory
):
    """A sensor is on while its class keeps being detected, then clears."""
    await _setup_with_detected_sensors_enabled(hass)
    assert hass.states.get(PERSON_DETECTED).state == STATE_OFF

    _detect(fake_sdk, "person", "motion")
    await hass.async_block_till_done()
    assert hass.states.get(PERSON_DETECTED).state == STATE_ON
    assert hass.states.get(CAR_DETECTED).state == STATE_OFF
    turned_on = hass.states.get(PERSON_DETECTED).last_updated

    # Another detection restarts the timer without rewriting the state.
    freezer.tick(timedelta(seconds=DETECTION_TIMEOUT - 10))
    async_fire_time_changed(hass)
    _detect(fake_sdk, "person")
    await hass.async_block_till_done()
    assert hass.states.get(PERSON_DETECTED).last_updated == turned_on

    freezer.tick(timedelta(seconds=DETECTION_TIMEOUT - 10))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(PERSON_DETECTED).state == STATE_ON

    # Other classes do not keep it on.
    _detect(fake_sdk, "car")
    freezer.tick(timedelta(seconds=20))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(PERSON_DETECTED).state == STATE_OFF
    assert hass.states.get(CAR_DETECTED).state == STATE_ON


async def test_detected_sensors_share_one_subscription(
    hass, fake_sdk, enable_custom_integrations
):
    """The event entity and every detected sensor share one listenDevice."""
    manager = fake_sdk.systemManager
    with patch.object(manager, "listenDevice", wraps=manager.listenDevice) as listen:
        await _setup_with_detected_sensors_enabled(hass)
    assert [call.args[:2] for call in listen.call_args_list] == [
        ("cam1", "ObjectDetector")
    ]


async def test_unload_cancels_pending_clear(
    hass, fake_sdk, enable_custom_integrations, freezer: FrozenDateTimeFactory
):
    """Unloading while a sensor is on cancels its timer and the subscription."""
    entry = await _setup_with_detected_sensors_enabled(hass)
    _detect(fake_sdk, "person")
    await hass.async_block_till_done()
    assert hass.states.get(PERSON_DETECTED).state == STATE_ON

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert ("cam1", "ObjectDetector") not in fake_sdk.systemManager.device_listeners

    freezer.tick(timedelta(seconds=DETECTION_TIMEOUT + 1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(PERSON_DETECTED).state == STATE_UNAVAILABLE
