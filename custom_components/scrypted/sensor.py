"""Sensors for the Scrypted integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    LIGHT_LUX,
    PERCENTAGE,
    EntityCategory,
    UnitOfDensity,
    UnitOfRatio,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import (
    ScryptedDeviceEntity,
    ScryptedEntityDescriptionMixin,
    async_setup_scrypted_platform,
    device_matches,
)


@dataclass(frozen=True, kw_only=True)
class ScryptedSensorDescription(
    SensorEntityDescription, ScryptedEntityDescriptionMixin
):
    """Describes a scrypted sensor."""


SENSORS: tuple[ScryptedSensorDescription, ...] = (
    ScryptedSensorDescription(
        key="temperature",
        name="Temperature",
        interface="Thermometer",
        state_property="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ScryptedSensorDescription(
        key="humidity",
        name="Humidity",
        interface="HumiditySensor",
        state_property="humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ScryptedSensorDescription(
        key="battery",
        name="Battery",
        interface="Battery",
        state_property="batteryLevel",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ScryptedSensorDescription(
        key="ambient_light",
        name="Ambient light",
        interface="AmbientLightSensor",
        state_property="ambientLight",
        device_class=SensorDeviceClass.ILLUMINANCE,
        native_unit_of_measurement=LIGHT_LUX,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ScryptedSensorDescription(
        key="luminance",
        name="Luminance",
        interface="LuminanceSensor",
        state_property="luminance",
        device_class=SensorDeviceClass.ILLUMINANCE,
        native_unit_of_measurement=LIGHT_LUX,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ScryptedSensorDescription(
        key="ultraviolet",
        name="UV index",
        interface="UltravioletSensor",
        state_property="ultraviolet",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ScryptedSensorDescription(
        key="co2",
        name="CO2",
        interface="CO2Sensor",
        state_property="co2ppm",
        device_class=SensorDeviceClass.CO2,
        native_unit_of_measurement=UnitOfRatio.PARTS_PER_MILLION,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ScryptedSensorDescription(
        key="pm25",
        name="PM2.5",
        interface="PM25Sensor",
        state_property="pm25Density",
        device_class=SensorDeviceClass.PM25,
        native_unit_of_measurement=UnitOfDensity.MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ScryptedSensorDescription(
        key="pm10",
        name="PM10",
        interface="PM10Sensor",
        state_property="pm10Density",
        device_class=SensorDeviceClass.PM10,
        native_unit_of_measurement=UnitOfDensity.MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ScryptedSensorDescription(
        key="voc",
        name="VOC",
        interface="VOCSensor",
        state_property="vocDensity",
        device_class=SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS,
        native_unit_of_measurement=UnitOfDensity.MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ScryptedSensorDescription(
        key="nox",
        name="NOx",
        interface="NOXSensor",
        state_property="noxDensity",
        native_unit_of_measurement=UnitOfDensity.MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ScryptedSensorDescription(
        key="air_quality",
        name="Air quality",
        interface="AirQualitySensor",
        state_property="airQuality",
        device_class=SensorDeviceClass.ENUM,
        options=["Excellent", "Good", "Fair", "Inferior", "Poor", "Unknown"],
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Scrypted sensors from config entry."""
    token = next(
        token
        for token, entry in hass.data[DOMAIN].items()
        if entry.entry_id == config_entry.entry_id
    )
    async_add_entities([ScryptedTokenSensor(config_entry, token)])

    client = config_entry.runtime_data.client

    def _discover(device_id: str) -> list[ScryptedSensor]:
        return [
            ScryptedSensor(client, config_entry, device_id, description)
            for description in SENSORS
            if device_matches(client, device_id, description.interface)
        ]

    await async_setup_scrypted_platform(
        hass, config_entry, async_add_entities, _discover
    )


class ScryptedTokenSensor(SensorEntity):
    """Representation of a Scrypted token sensor."""

    def __init__(
        self,
        config_entry: ConfigEntry,
        token: str,
    ) -> None:
        """Initialize a ScryptedTokenSensor entity."""
        self._attr_name = f"{DOMAIN.title()} token: {config_entry.data[CONF_HOST]}"
        self._attr_unique_id = config_entry.data[CONF_HOST]
        self._attr_native_value = token
        self._attr_icon = "mdi:shield-key"
        self._attr_should_poll = False
        self._attr_extra_state_attributes = {CONF_HOST: config_entry.data[CONF_HOST]}


class ScryptedSensor(ScryptedDeviceEntity, SensorEntity):
    """A numeric/enum scrypted device property."""

    entity_description: ScryptedSensorDescription

    @property
    def native_value(self):
        """Return the converted native value, or None while the property is unset."""
        value = self.raw_value
        if value is None:
            return None
        return self.entity_description.value_fn(value)
