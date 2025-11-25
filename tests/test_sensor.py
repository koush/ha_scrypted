from __future__ import annotations

import pytest

from custom_components.scrypted import sensor
from custom_components.scrypted.const import DOMAIN
from homeassistant.const import CONF_HOST

from pytest_homeassistant_custom_component.common import MockConfigEntry


def test_sensor_attributes():
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "example"})
    entity = sensor.ScryptedTokenSensor(entry, "token")
    assert entity.name == "Scrypted token: example"
    assert entity.native_value == "token"
    assert entity.extra_state_attributes[CONF_HOST] == "example"


@pytest.mark.asyncio
async def test_async_setup_entry_adds_token_sensor(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "example"})
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})["token"] = entry
    added = []

    def _add_entities(entities):
        added.extend(entities)

    await sensor.async_setup_entry(hass, entry, _add_entities)
    assert len(added) == 1
    assert added[0].native_value == "token"
