"""Binary sensors for Scrypted device states."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import (
    ScryptedDeviceEntity,
    ScryptedEntityDescriptionMixin,
    async_setup_scrypted_platform,
    device_matches,
)


@dataclass(frozen=True, kw_only=True)
class ScryptedBinarySensorDescription(
    BinarySensorEntityDescription, ScryptedEntityDescriptionMixin
):
    """Describes a scrypted binary sensor."""


BINARY_SENSORS: tuple[ScryptedBinarySensorDescription, ...] = (
    ScryptedBinarySensorDescription(
        key="motion",
        name="Motion",
        interface="MotionSensor",
        state_property="motionDetected",
        device_class=BinarySensorDeviceClass.MOTION,
    ),
    ScryptedBinarySensorDescription(
        key="binary_state",
        name="Binary state",
        interface="BinarySensor",
        state_property="binaryState",
    ),
    ScryptedBinarySensorDescription(
        key="audio",
        name="Sound",
        interface="AudioSensor",
        state_property="audioDetected",
        device_class=BinarySensorDeviceClass.SOUND,
    ),
    ScryptedBinarySensorDescription(
        key="occupancy",
        name="Occupancy",
        interface="OccupancySensor",
        state_property="occupied",
        device_class=BinarySensorDeviceClass.OCCUPANCY,
    ),
    ScryptedBinarySensorDescription(
        key="flooded",
        name="Flooded",
        interface="FloodSensor",
        state_property="flooded",
        device_class=BinarySensorDeviceClass.MOISTURE,
    ),
    ScryptedBinarySensorDescription(
        key="entry_open",
        name="Entry open",
        interface="EntrySensor",
        state_property="entryOpen",
        device_class=BinarySensorDeviceClass.DOOR,
        # entryOpen can be True/False/'jammed'
        value_fn=lambda value: value is True,
    ),
    ScryptedBinarySensorDescription(
        key="power",
        name="Power",
        interface="PowerSensor",
        state_property="powerDetected",
        device_class=BinarySensorDeviceClass.POWER,
    ),
    ScryptedBinarySensorDescription(
        key="online",
        name="Online",
        interface="Online",
        state_property="online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ScryptedBinarySensorDescription(
        key="tampered",
        name="Tampered",
        interface="TamperSensor",
        state_property="tampered",
        device_class=BinarySensorDeviceClass.TAMPER,
        entity_category=EntityCategory.DIAGNOSTIC,
        # tampered is a TamperState string or falsy
        value_fn=bool,
    ),
    ScryptedBinarySensorDescription(
        key="charging",
        name="Charging",
        interface="Charger",
        state_property="chargeState",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda value: value in ("charging", "trickle"),
    ),
    ScryptedBinarySensorDescription(
        key="sleeping",
        name="Sleeping",
        interface="Sleep",
        state_property="sleeping",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up scrypted binary sensors."""
    client = config_entry.runtime_data.client

    def _discover(device_id: str) -> list[ScryptedBinarySensor]:
        return [
            ScryptedBinarySensor(client, config_entry, device_id, description)
            for description in BINARY_SENSORS
            if device_matches(client, device_id, description.interface)
        ]

    await async_setup_scrypted_platform(
        hass, config_entry, async_add_entities, _discover
    )


class ScryptedBinarySensor(ScryptedDeviceEntity, BinarySensorEntity):
    """A boolean scrypted device property."""

    entity_description: ScryptedBinarySensorDescription

    @property
    def is_on(self) -> bool | None:
        """Return the boolean state, or None while the property is unset."""
        value = self.raw_value
        if value is None:
            return None
        return bool(self.entity_description.value_fn(value))
