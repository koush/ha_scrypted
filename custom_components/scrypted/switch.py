"""Switch entities for controllable scrypted devices."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scrypted_sdk import ScryptedInterface

from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription,
)
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
class ScryptedSwitchDescription(
    SwitchEntityDescription, ScryptedEntityDescriptionMixin
):
    """Describe a scrypted switch."""


# Keyed by scrypted device type; both share key="switch" so unique_ids are stable
# if a device is later reclassified between Switch and Outlet.
SWITCH_DESCRIPTIONS: dict[str, ScryptedSwitchDescription] = {
    "Switch": ScryptedSwitchDescription(
        key="switch",
        name=None,
        device_class=SwitchDeviceClass.SWITCH,
        interface=ScryptedInterface.OnOff.value,
        state_property="on",
    ),
    "Outlet": ScryptedSwitchDescription(
        key="switch",
        name=None,
        device_class=SwitchDeviceClass.OUTLET,
        interface=ScryptedInterface.OnOff.value,
        state_property="on",
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up scrypted switches."""
    client = config_entry.runtime_data.client

    def _discover(device_id: str) -> list[ScryptedSwitch]:
        if client.sdk is None:
            return []
        device = client.sdk.systemManager.getDeviceById(device_id)
        if device is None:
            return []
        description = SWITCH_DESCRIPTIONS.get(device.type or "")
        if description is None:
            return []
        if not device_matches(client, device_id, description.interface):
            return []
        return [ScryptedSwitch(client, config_entry, device_id, description)]

    await async_setup_scrypted_platform(
        hass, config_entry, async_add_entities, _discover
    )


class ScryptedSwitch(ScryptedDeviceEntity, SwitchEntity):
    """OnOff control for scrypted Switch/Outlet devices."""

    entity_description: ScryptedSwitchDescription

    @property
    def is_on(self) -> bool | None:
        """Return True if the device reports itself on."""
        return self.raw_value

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the device on."""
        await self._async_device_command("turnOn")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the device off."""
        await self._async_device_command("turnOff")
