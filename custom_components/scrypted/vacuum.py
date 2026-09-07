"""Vacuum entities for scrypted Vacuum devices."""

from __future__ import annotations

from dataclasses import dataclass

from scrypted_sdk import ScryptedInterface

from homeassistant.components.vacuum import (
    StateVacuumEntity,
    StateVacuumEntityDescription,
    VacuumActivity,
    VacuumEntityFeature,
)
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
class ScryptedVacuumDescription(
    StateVacuumEntityDescription, ScryptedEntityDescriptionMixin
):
    """Describes a scrypted vacuum."""


VACUUM = ScryptedVacuumDescription(
    key="vacuum",
    name=None,
    interface=ScryptedInterface.StartStop.value,
    state_property="running",
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up scrypted vacuums."""
    client = config_entry.runtime_data.client

    def _discover(device_id: str) -> list[ScryptedVacuum]:
        device = exposed_device(client, device_id)
        if (
            device is None
            or device.type != "Vacuum"
            or VACUUM.interface not in (device.interfaces or [])
        ):
            return []
        return [ScryptedVacuum(client, config_entry, device_id, VACUUM)]

    await async_setup_scrypted_platform(
        hass, config_entry, async_add_entities, _discover
    )


class ScryptedVacuum(ScryptedDeviceEntity, StateVacuumEntity):
    """StartStop/Pause/Dock control for scrypted vacuums."""

    entity_description: ScryptedVacuumDescription

    def __init__(self, client, entry, device_id, description) -> None:
        """Derive supported features from the device's Pause/Dock interfaces."""
        super().__init__(client, entry, device_id, description)
        device = client.sdk.systemManager.getDeviceById(device_id)
        interfaces = set(device.interfaces or [])
        features = (
            VacuumEntityFeature.START
            | VacuumEntityFeature.STOP
            | VacuumEntityFeature.STATE
        )
        self._has_pause = ScryptedInterface.Pause.value in interfaces
        if self._has_pause:
            features |= VacuumEntityFeature.PAUSE
        if ScryptedInterface.Dock.value in interfaces:
            features |= VacuumEntityFeature.RETURN_HOME
        self._attr_supported_features = features

    @property
    def activity(self) -> VacuumActivity | None:
        """Map running/paused/docked properties to a VacuumActivity."""
        device = self.device
        if device is None:
            return None
        if device.running:
            return VacuumActivity.PAUSED if device.paused else VacuumActivity.CLEANING
        if device.docked:
            return VacuumActivity.DOCKED
        return VacuumActivity.IDLE

    async def async_start(self) -> None:
        """Resume if paused, otherwise start cleaning."""
        device = self.device
        if self._has_pause and device is not None and device.paused:
            await self._async_device_command("resume")
            return
        await self._async_device_command("start")

    async def async_stop(self, **kwargs) -> None:
        """Stop cleaning."""
        await self._async_device_command("stop")

    async def async_pause(self) -> None:
        """Pause cleaning."""
        await self._async_device_command("pause")

    async def async_return_to_base(self, **kwargs) -> None:
        """Send the vacuum back to its dock."""
        await self._async_device_command("dock")
