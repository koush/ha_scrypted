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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import SIGNAL_NEW_DEVICE
from .entity import (
    ScryptedDeviceEntity,
    ScryptedEntityDescriptionMixin,
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
        value_fn=lambda value: bool(value),
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
    if client is None:
        return
    known: set[tuple[str, str]] = set()

    @callback
    def _add_for_device(device_id: str) -> None:
        entities = []
        for description in BINARY_SENSORS:
            if (device_id, description.key) in known:
                continue
            if not device_matches(client, device_id, description.interface):
                continue
            known.add((device_id, description.key))
            entities.append(
                ScryptedBinarySensor(client, config_entry, device_id, description)
            )
        if entities:
            async_add_entities(entities)

    for device_id in client.device_ids:
        _add_for_device(device_id)

    config_entry.async_on_unload(
        async_dispatcher_connect(
            hass, SIGNAL_NEW_DEVICE.format(config_entry.entry_id), _add_for_device
        )
    )


class ScryptedBinarySensor(ScryptedDeviceEntity, BinarySensorEntity):
    """A boolean scrypted device property."""

    entity_description: ScryptedBinarySensorDescription

    @property
    def is_on(self) -> bool | None:
        value = self.raw_value
        if value is None:
            return None
        return bool(self.entity_description.value_fn(value))
