"""Switch entities for controllable scrypted devices."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
from .sdk_compat import ScryptedInterface

SWITCH_TYPES = {"Switch", "Outlet"}


@dataclass(frozen=True, kw_only=True)
class ScryptedSwitchDescription(SwitchEntityDescription, ScryptedEntityDescriptionMixin):
    """Describes a scrypted switch."""


SWITCH = ScryptedSwitchDescription(
    key="switch",
    name=None,
    interface=ScryptedInterface.OnOff.value,
    state_property="on",
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up scrypted switches."""
    client = config_entry.runtime_data.client

    def _discover(device_id: str) -> list[ScryptedSwitch]:
        device = client.sdk.systemManager.getDeviceById(device_id)
        if device is None or (device.type or "") not in SWITCH_TYPES:
            return []
        if not device_matches(client, device_id, SWITCH.interface):
            return []
        return [ScryptedSwitch(client, config_entry, device_id, SWITCH)]

    await async_setup_scrypted_platform(
        hass, config_entry, async_add_entities, _discover
    )


class ScryptedSwitch(ScryptedDeviceEntity, SwitchEntity):
    """OnOff control for scrypted Switch/Outlet devices."""

    entity_description: ScryptedSwitchDescription

    def __init__(self, client, entry, device_id, description) -> None:
        super().__init__(client, entry, device_id, description)
        device = client.sdk.systemManager.getDeviceById(device_id)
        self._attr_device_class = (
            SwitchDeviceClass.OUTLET
            if device.type == "Outlet"
            else SwitchDeviceClass.SWITCH
        )

    @property
    def is_on(self) -> bool | None:
        return self.raw_value

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_device_command("turnOn")

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_device_command("turnOff")
