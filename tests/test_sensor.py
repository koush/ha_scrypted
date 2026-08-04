"""Tests for the Scrypted sensor platform."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from homeassistant.const import CONF_HOST

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.scrypted import sensor
from custom_components.scrypted.const import DOMAIN
from custom_components.scrypted.sensor import SENSORS, ScryptedSensor
from tests.test_binary_sensor import setup_entry


def test_sensor_attributes():
    """Test case for test_sensor_attributes."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "example"})
    entity = sensor.ScryptedTokenSensor(entry, "token")
    assert entity.name == "Scrypted token: example"
    assert entity.native_value == "token"
    assert entity.extra_state_attributes[CONF_HOST] == "example"


@pytest.mark.asyncio
async def test_async_setup_entry_adds_token_sensor(hass):
    """Test case for test_async_setup_entry_adds_token_sensor."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "example"})
    entry.add_to_hass(hass)
    entry.runtime_data = SimpleNamespace(client=None)
    hass.data.setdefault(DOMAIN, {})["token"] = entry
    added = []

    def _add_entities(entities):
        added.extend(entities)

    await sensor.async_setup_entry(hass, entry, _add_entities)
    assert len(added) == 1
    assert added[0].native_value == "token"


async def test_device_sensors_created(hass, fake_sdk, enable_custom_integrations):
    await setup_entry(hass)

    temp = hass.states.get("sensor.basement_basement_leak_temperature")
    assert temp is not None
    assert temp.state == "21.5"
    assert temp.attributes["device_class"] == "temperature"

    battery = hass.states.get("sensor.porch_front_door_cam_battery")
    assert battery is not None
    assert battery.state == "80"


async def test_sensor_updates_on_event(hass, fake_sdk, enable_custom_integrations):
    await setup_entry(hass)
    fake_sdk.systemManager.set_property("leak1", "temperature", 25.0)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.basement_basement_leak_temperature").state == "25.0"


def test_sensor_native_value_none(fake_sdk):
    client = SimpleNamespace(sdk=fake_sdk, connected=True)
    entry = MockConfigEntry(domain=DOMAIN)
    description = next(d for d in SENSORS if d.key == "temperature")
    entity = ScryptedSensor(client, entry, "leak1", description)
    fake_sdk.systemManager.systemState["leak1"].pop("temperature")
    assert entity.native_value is None
