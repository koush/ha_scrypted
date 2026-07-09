"""Lock entities for scrypted Lock devices."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.lock import LockEntity, LockEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import (
    ScryptedDeviceEntity,
    ScryptedEntityDescriptionMixin,
    async_setup_scrypted_platform,
    device_matches,
)


@dataclass(frozen=True, kw_only=True)
class ScryptedLockDescription(LockEntityDescription, ScryptedEntityDescriptionMixin):
    """Describes a scrypted lock."""


LOCK = ScryptedLockDescription(
    key="lock",
    name=None,
    interface="Lock",
    state_property="lockState",
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up scrypted locks."""
    client = config_entry.runtime_data.client

    def _discover(device_id: str) -> list[ScryptedLock]:
        device = client.sdk.systemManager.getDeviceById(device_id)
        if device is None or device.type != "Lock":
            return []
        if not device_matches(client, device_id, LOCK.interface):
            return []
        return [ScryptedLock(client, config_entry, device_id, LOCK)]

    await async_setup_scrypted_platform(
        hass, config_entry, async_add_entities, _discover
    )


class ScryptedLock(ScryptedDeviceEntity, LockEntity):
    """Lock/unlock control backed by scrypted lockState."""

    entity_description: ScryptedLockDescription

    @property
    def is_locked(self) -> bool | None:
        value = self.raw_value
        return None if value is None else value == "Locked"

    @property
    def is_jammed(self) -> bool:
        return self.raw_value == "Jammed"

    async def async_lock(self, **kwargs: Any) -> None:
        await self._async_device_command("lock")

    async def async_unlock(self, **kwargs: Any) -> None:
        await self._async_device_command("unlock")
