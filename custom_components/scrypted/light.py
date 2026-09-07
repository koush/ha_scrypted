"""Light entities for scrypted Light devices."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from scrypted_sdk import ScryptedInterface

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
    LightEntityDescription,
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

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class ScryptedLightDescription(LightEntityDescription, ScryptedEntityDescriptionMixin):
    """Describes a scrypted light."""


LIGHT = ScryptedLightDescription(
    key="light",
    name=None,
    interface=ScryptedInterface.OnOff.value,
    state_property="on",
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up scrypted lights."""
    client = config_entry.runtime_data.client

    def _discover(device_id: str) -> list[ScryptedLight]:
        device = exposed_device(client, device_id)
        if (
            device is None
            or device.type != "Light"
            or LIGHT.interface not in (device.interfaces or [])
        ):
            return []
        return [ScryptedLight(client, config_entry, device_id, LIGHT)]

    await async_setup_scrypted_platform(
        hass, config_entry, async_add_entities, _discover
    )


class ScryptedLight(ScryptedDeviceEntity, LightEntity):
    """OnOff/Brightness/color control for scrypted lights."""

    entity_description: ScryptedLightDescription

    def __init__(self, client, entry, device_id, description) -> None:
        """Initialize the light with color modes derived from its interfaces."""
        super().__init__(client, entry, device_id, description)
        device = client.sdk.systemManager.getDeviceById(device_id)
        interfaces = set(device.interfaces or [])
        modes: set[ColorMode] = set()
        if ScryptedInterface.ColorSettingHsv.value in interfaces:
            modes.add(ColorMode.HS)
        elif ScryptedInterface.ColorSettingRgb.value in interfaces:
            modes.add(ColorMode.RGB)
        if ScryptedInterface.ColorSettingTemperature.value in interfaces:
            modes.add(ColorMode.COLOR_TEMP)
        if not modes:
            modes = (
                {ColorMode.BRIGHTNESS}
                if ScryptedInterface.Brightness.value in interfaces
                else {ColorMode.ONOFF}
            )
        self._attr_supported_color_modes = modes

    async def async_added_to_hass(self) -> None:
        """Subscribe to updates and fetch the color temperature range."""
        await super().async_added_to_hass()
        if ColorMode.COLOR_TEMP not in self._attr_supported_color_modes:
            return
        try:
            self._attr_max_color_temp_kelvin = round(
                await self.device.getTemperatureMaxK()
            )
            self._attr_min_color_temp_kelvin = round(
                await self.device.getTemperatureMinK()
            )
        except Exception:  # noqa: BLE001 - fall back to HA default range
            _LOGGER.debug(
                "kelvin range fetch failed for %s", self.device_id, exc_info=True
            )

    @property
    def is_on(self) -> bool | None:
        """Return whether the light is on."""
        return self.raw_value

    @property
    def brightness(self) -> int | None:
        """Return the brightness on the 0-255 scale."""
        device = self.device
        value = device.brightness if device else None
        return None if value is None else round(value * 255 / 100)

    @property
    def color_temp_kelvin(self) -> int | None:
        """Return the color temperature in kelvin."""
        device = self.device
        value = device.colorTemperature if device else None
        return None if value is None else round(value)

    @property
    def hs_color(self) -> tuple[float, float] | None:
        """Return the hue/saturation color, or None if not reported."""
        device = self.device
        hsv = (device.hsv if device else None) or {}
        if hsv.get("h") is None:
            return None
        return (hsv["h"], (hsv.get("s") or 0) * 100)

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        """Return the RGB color, or None if not reported."""
        device = self.device
        rgb = (device.rgb if device else None) or {}
        if rgb.get("r") is None:
            return None
        return (rgb["r"], rgb.get("g") or 0, rgb.get("b") or 0)

    @property
    def color_mode(self) -> ColorMode:
        """Return the active color mode, preferring color while saturated."""
        modes = self._attr_supported_color_modes
        if len(modes) == 1:
            return next(iter(modes))
        # temp + one color mode: report color while saturated, else temp
        if ColorMode.HS in modes:
            hs = self.hs_color
            saturated = bool(hs and hs[1])
        else:
            rgb = self.rgb_color
            saturated = bool(rgb and len(set(rgb)) > 1)
        if saturated:
            return ColorMode.HS if ColorMode.HS in modes else ColorMode.RGB
        return ColorMode.COLOR_TEMP

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light and apply any requested brightness or color."""
        await self._async_device_command("turnOn")
        if ATTR_BRIGHTNESS in kwargs:
            await self._async_device_command(
                "setBrightness", round(kwargs[ATTR_BRIGHTNESS] * 100 / 255)
            )
        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            await self._async_device_command(
                "setColorTemperature", kwargs[ATTR_COLOR_TEMP_KELVIN]
            )
        if ATTR_HS_COLOR in kwargs:
            hue, saturation = kwargs[ATTR_HS_COLOR]
            device = self.device
            value = ((device.hsv if device else None) or {}).get("v") or 1
            await self._async_device_command("setHsv", hue, saturation / 100, value)
        if ATTR_RGB_COLOR in kwargs:
            await self._async_device_command("setRgb", *kwargs[ATTR_RGB_COLOR])

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light."""
        await self._async_device_command("turnOff")
