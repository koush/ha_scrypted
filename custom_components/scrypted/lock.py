"""Lock entities for controllable scrypted devices."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import async_setup_scrypted_platform


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up scrypted locks."""
    await async_setup_scrypted_platform(
        hass, config_entry, async_add_entities, lambda device_id: []
    )
