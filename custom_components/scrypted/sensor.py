"""Representation of Z-Wave sensors."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Scrypted token sensor from config entry."""
    token = next(
        token
        for token, entry in hass.data[DOMAIN].items()
        if entry.entry_id == config_entry.entry_id
    )
    async_add_entities([ScryptedTokenSensor(config_entry, token)])


class ScryptedTokenSensor(SensorEntity):
    """Representation of a Scrypted token sensor."""

    def __init__(
        self,
        config_entry: ConfigEntry,
        token: str,
    ) -> None:
        """Initialize a ScryptedTokenSensor entity."""
        self._attr_name = f"{DOMAIN.title()} token: {config_entry.data[CONF_HOST]}"
        self._attr_unique_id = config_entry.data[CONF_HOST]
        self._attr_native_value = token
        self._attr_icon = "mdi:shield-key"
        self._attr_should_poll = False
        self._attr_extra_state_attributes = {CONF_HOST: config_entry.data[CONF_HOST]}
