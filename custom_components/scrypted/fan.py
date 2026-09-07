"""Fan entities for scrypted Fan devices."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scrypted_sdk import ScryptedInterface

from homeassistant.components.fan import (
    FanEntity,
    FanEntityDescription,
    FanEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import (
    ScryptedDeviceEntity,
    ScryptedEntityDescriptionMixin,
    async_setup_scrypted_platform,
    exposed_device,
)


@dataclass(frozen=True, kw_only=True)
class ScryptedFanDescription(FanEntityDescription, ScryptedEntityDescriptionMixin):
    """Describes a scrypted fan."""


FAN = ScryptedFanDescription(
    key="fan",
    name=None,
    interface=ScryptedInterface.Fan.value,
    state_property="fan",
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up scrypted fans."""
    client = config_entry.runtime_data.client

    def _discover(device_id: str) -> list[ScryptedFan]:
        device = exposed_device(client, device_id)
        if (
            device is None
            or device.type != "Fan"
            or FAN.interface not in (device.interfaces or [])
        ):
            return []
        return [ScryptedFan(client, config_entry, device_id, FAN)]

    await async_setup_scrypted_platform(
        hass, config_entry, async_add_entities, _discover
    )


class ScryptedFan(ScryptedDeviceEntity, FanEntity):
    """Speed/preset control backed by scrypted FanStatus."""

    entity_description: ScryptedFanDescription
    _attr_supported_features = (
        FanEntityFeature.SET_SPEED
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
    )

    def __init__(self, client, entry, device_id, description) -> None:
        """Initialize the fan, capturing preset modes from the initial FanStatus."""
        super().__init__(client, entry, device_id, description)
        status = self.raw_value or {}
        modes = status.get("availableModes") or []
        if modes:
            self._attr_preset_modes = list(modes)
            self._attr_supported_features |= FanEntityFeature.PRESET_MODE
        self._last_speed: int | None = status.get("speed") or None

    @property
    def _status(self) -> dict:
        return self.raw_value or {}

    @property
    def _max_speed(self) -> int:
        return self._status.get("maxSpeed") or 1

    @property
    def percentage(self) -> int | None:
        """Return the current speed as a percentage of maxSpeed."""
        speed = self._status.get("speed")
        return None if speed is None else min(100, round(speed * 100 / self._max_speed))

    @property
    def preset_mode(self) -> str | None:
        """Return the active fan mode."""
        return self._status.get("mode")

    @callback
    def _handle_device_update(self, event_details: dict, value: Any) -> None:
        if self._status.get("speed"):
            self._last_speed = self._status["speed"]
        super()._handle_device_update(event_details, value)

    async def async_set_percentage(self, percentage: int) -> None:
        """Scale the percentage to the device speed range and set it."""
        speed = round(percentage * self._max_speed / 100)
        await self._async_device_command("setFan", {"speed": speed})

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the fan mode."""
        await self._async_device_command("setFan", {"mode": preset_mode})

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Turn on the fan using the requested or last known speed or mode."""
        if preset_mode is not None:
            await self.async_set_preset_mode(preset_mode)
        if percentage is not None:
            await self.async_set_percentage(percentage)
        elif preset_mode is None:
            await self._async_device_command(
                "setFan", {"speed": self._last_speed or self._max_speed}
            )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the fan by setting speed to zero."""
        await self._async_device_command("setFan", {"speed": 0})
