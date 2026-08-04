"""Cover entities for scrypted Entry/Garage/WindowCovering devices."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityDescription,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from scrypted_sdk import ScryptedInterface

from .entity import (
    ScryptedDeviceEntity,
    ScryptedEntityDescriptionMixin,
    async_setup_scrypted_platform,
    device_matches,
)

COVER_DEVICE_CLASSES = {
    "Garage": CoverDeviceClass.GARAGE,
    "Entry": CoverDeviceClass.DOOR,
    "WindowCovering": CoverDeviceClass.SHADE,
}


@dataclass(frozen=True, kw_only=True)
class ScryptedCoverDescription(CoverEntityDescription, ScryptedEntityDescriptionMixin):
    """Describes a scrypted cover."""


COVER = ScryptedCoverDescription(
    key="cover",
    name=None,
    interface=ScryptedInterface.Entry.value,
    state_property="entryOpen",
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up scrypted covers."""
    client = config_entry.runtime_data.client

    def _discover(device_id: str) -> list[ScryptedCover]:
        device = client.sdk.systemManager.getDeviceById(device_id)
        if device is None or (device.type or "") not in COVER_DEVICE_CLASSES:
            return []
        if not device_matches(client, device_id, COVER.interface):
            return []
        return [ScryptedCover(client, config_entry, device_id, COVER)]

    await async_setup_scrypted_platform(
        hass, config_entry, async_add_entities, _discover
    )


class ScryptedCover(ScryptedDeviceEntity, CoverEntity):
    """Open/close control backed by scrypted Entry (+EntrySensor state)."""

    entity_description: ScryptedCoverDescription
    _attr_supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE

    def __init__(self, client, entry, device_id, description) -> None:
        super().__init__(client, entry, device_id, description)
        device = client.sdk.systemManager.getDeviceById(device_id)
        self._attr_device_class = COVER_DEVICE_CLASSES[device.type]
        self._has_sensor = ScryptedInterface.EntrySensor.value in (
            device.interfaces or []
        )
        self._attr_assumed_state = not self._has_sensor

    @property
    def is_closed(self) -> bool | None:
        if not self._has_sensor:
            return None
        value = self.raw_value
        if value is None or value == "jammed":
            return None
        return not value

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self._async_device_command("openEntry")

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self._async_device_command("closeEntry")
