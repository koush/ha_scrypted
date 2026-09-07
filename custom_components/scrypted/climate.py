"""Climate entities for scrypted Thermostat devices."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scrypted_sdk import ScryptedInterface

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    ClimateEntity,
    ClimateEntityDescription,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import (
    ScryptedDeviceEntity,
    ScryptedEntityDescriptionMixin,
    async_setup_scrypted_platform,
    device_matches,
)

SCRYPTED_TO_HVAC = {
    "Off": HVACMode.OFF,
    "Heat": HVACMode.HEAT,
    "Cool": HVACMode.COOL,
    "HeatCool": HVACMode.HEAT_COOL,
    "Auto": HVACMode.AUTO,
    "FanOnly": HVACMode.FAN_ONLY,
    "Dry": HVACMode.DRY,
}
HVAC_TO_SCRYPTED = {value: key for key, value in SCRYPTED_TO_HVAC.items()}
ACTIVE_TO_ACTION = {
    "Off": HVACAction.IDLE,
    "Heat": HVACAction.HEATING,
    "Cool": HVACAction.COOLING,
    "Dry": HVACAction.DRYING,
    "FanOnly": HVACAction.FAN,
}


@dataclass(frozen=True, kw_only=True)
class ScryptedClimateDescription(
    ClimateEntityDescription, ScryptedEntityDescriptionMixin
):
    """Describes a scrypted thermostat."""


CLIMATE = ScryptedClimateDescription(
    key="climate",
    name=None,
    interface=ScryptedInterface.TemperatureSetting.value,
    state_property="temperatureSetting",
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up scrypted thermostats."""
    client = config_entry.runtime_data.client

    def _discover(device_id: str) -> list[ScryptedThermostat]:
        device = client.sdk.systemManager.getDeviceById(device_id)
        if device is None or device.type != "Thermostat":
            return []
        if not device_matches(client, device_id, CLIMATE.interface):
            return []
        return [ScryptedThermostat(client, config_entry, device_id, CLIMATE)]

    await async_setup_scrypted_platform(
        hass, config_entry, async_add_entities, _discover
    )


class ScryptedThermostat(ScryptedDeviceEntity, ClimateEntity):
    """Thermostat control backed by scrypted TemperatureSetting."""

    entity_description: ScryptedClimateDescription
    _attr_temperature_unit = UnitOfTemperature.CELSIUS

    @property
    def _setting(self) -> dict:
        return self.raw_value or {}

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Report ranged or single setpoint support based on the current setpoint shape."""
        features = ClimateEntityFeature.TURN_OFF
        if isinstance(self._setting.get("setpoint"), (list, tuple)):
            features |= ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        else:
            features |= ClimateEntityFeature.TARGET_TEMPERATURE
        return features

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Translate scrypted availableModes to HVAC modes, defaulting to OFF."""
        modes = [
            SCRYPTED_TO_HVAC[mode]
            for mode in self._setting.get("availableModes") or []
            if mode in SCRYPTED_TO_HVAC
        ]
        return modes or [HVACMode.OFF]

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return the current scrypted mode as an HVAC mode."""
        mode = self._setting.get("mode")
        return SCRYPTED_TO_HVAC.get(mode) if mode is not None else None

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return the current scrypted activeMode as an HVAC action."""
        active = self._setting.get("activeMode")
        return ACTIVE_TO_ACTION.get(active) if active is not None else None

    @property
    def target_temperature(self) -> float | None:
        """Return the single setpoint, or None when the setpoint is a range."""
        setpoint = self._setting.get("setpoint")
        return None if isinstance(setpoint, (list, tuple)) else setpoint

    @property
    def target_temperature_low(self) -> float | None:
        """Return the lower bound of a ranged setpoint."""
        setpoint = self._setting.get("setpoint")
        return setpoint[0] if isinstance(setpoint, (list, tuple)) else None

    @property
    def target_temperature_high(self) -> float | None:
        """Return the upper bound of a ranged setpoint."""
        setpoint = self._setting.get("setpoint")
        return setpoint[1] if isinstance(setpoint, (list, tuple)) else None

    @property
    def current_temperature(self) -> float | None:
        """Return the Thermometer reading."""
        device = self.device
        return device.temperature if device else None

    @property
    def current_humidity(self) -> float | None:
        """Return the HumiditySensor reading."""
        device = self.device
        return device.humidity if device else None

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the scrypted thermostat mode."""
        await self._async_device_command(
            "setTemperature", {"mode": HVAC_TO_SCRYPTED[hvac_mode]}
        )

    async def async_turn_off(self) -> None:
        """Turn the thermostat off."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Send a single or ranged setpoint and optional mode to the thermostat."""
        command: dict[str, Any] = {}
        if ATTR_TARGET_TEMP_LOW in kwargs and ATTR_TARGET_TEMP_HIGH in kwargs:
            command["setpoint"] = [
                kwargs[ATTR_TARGET_TEMP_LOW],
                kwargs[ATTR_TARGET_TEMP_HIGH],
            ]
        elif ATTR_TEMPERATURE in kwargs:
            command["setpoint"] = kwargs[ATTR_TEMPERATURE]
        if kwargs.get(ATTR_HVAC_MODE) in HVAC_TO_SCRYPTED:
            command["mode"] = HVAC_TO_SCRYPTED[kwargs[ATTR_HVAC_MODE]]
        if command:
            await self._async_device_command("setTemperature", command)
