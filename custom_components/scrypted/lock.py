"""Lock entities for scrypted Lock devices."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scrypted_sdk import ScryptedInterface

from homeassistant.components.lock import LockEntity, LockEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import (
    ScryptedDeviceEntity,
    ScryptedEntityDescriptionMixin,
    async_setup_scrypted_platform,
    exposed_device,
)


@dataclass(frozen=True, kw_only=True)
class ScryptedLockDescription(LockEntityDescription, ScryptedEntityDescriptionMixin):
    """Describe a scrypted lock."""


LOCK = ScryptedLockDescription(
    key="lock",
    name=None,
    interface=ScryptedInterface.Lock.value,
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
        device = exposed_device(client, device_id)
        if (
            device is None
            or device.type != "Lock"
            or LOCK.interface not in (device.interfaces or [])
        ):
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
        """Return True when lockState is Locked, None when unknown."""
        value = self.raw_value
        return None if value is None else value == "Locked"

    @property
    def is_jammed(self) -> bool:
        """Return True when the lock reports a jammed mechanism."""
        return self.raw_value == "Jammed"

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the device."""
        await self._async_device_command("lock")

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the device."""
        await self._async_device_command("unlock")
