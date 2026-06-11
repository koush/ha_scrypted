"""Base entity for Scrypted devices."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .client import ScryptedClient
from .const import (
    DOMAIN,
    EXCLUDED_DEVICE_TYPES,
    SIGNAL_CONNECTION,
    SIGNAL_DEVICE_UPDATE,
)
from .sdk_compat import ScryptedInterface


@dataclass(frozen=True, kw_only=True)
class ScryptedEntityDescriptionMixin:
    """Scrypted-specific description fields.

    interface: the ScryptedInterface that must be present for discovery.
    state_property: the systemState property backing this entity's value.
    value_fn: converts the raw scrypted value to the HA native value.
    """

    interface: str
    state_property: str | None = None
    value_fn: Callable[[Any], Any] = lambda value: value


def device_matches(sdk, device_id: str, interface: str) -> bool:
    """Return True if the device should produce an entity for interface."""
    device = sdk.systemManager.getDeviceById(device_id)
    if device is None:
        return False
    if (device.type or "Unknown") in EXCLUDED_DEVICE_TYPES:
        return False
    return interface in (device.interfaces or [])


class ScryptedDeviceEntity(Entity):
    """Common behavior: device info, availability, push updates."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(
        self,
        client: ScryptedClient,
        entry: ConfigEntry,
        device_id: str,
        description,
    ) -> None:
        self.client = client
        self.entry = entry
        self.device_id = device_id
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{device_id}_{description.key}"

        device = client.sdk.systemManager.getDeviceById(device_id)
        info = device.info or {}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{device_id}")},
            name=device.name,
            manufacturer=info.get("manufacturer"),
            model=info.get("model"),
            sw_version=info.get("version") or info.get("firmware"),
            serial_number=info.get("serialNumber"),
            suggested_area=device.room,
            via_device=(DOMAIN, entry.entry_id),
            configuration_url=info.get("managementUrl"),
        )

    @property
    def device(self):
        """Live DeviceProxy; property reads are local dict lookups."""
        if not self.client.sdk:
            return None
        return self.client.sdk.systemManager.getDeviceById(self.device_id)

    @property
    def raw_value(self) -> Any:
        """Raw scrypted value of this entity's backing property."""
        device = self.device
        prop = self.entity_description.state_property
        if device is None or prop is None:
            return None
        return getattr(device, prop)

    @property
    def available(self) -> bool:
        if not self.client.connected:
            return False
        device = self.device
        if device is None:
            return False
        if (
            ScryptedInterface.Online.value in (device.interfaces or [])
            and device.online is False
        ):
            return False
        return True

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_DEVICE_UPDATE.format(self.entry.entry_id, self.device_id),
                self._handle_device_update,
            )
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_CONNECTION.format(self.entry.entry_id),
                self._handle_connection_change,
            )
        )

    @callback
    def _handle_device_update(self, event_details: dict, value: Any) -> None:
        self.async_write_ha_state()

    @callback
    def _handle_connection_change(self, connected: bool) -> None:
        self.async_write_ha_state()
