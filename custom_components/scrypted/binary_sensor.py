"""Binary sensors for Scrypted device states."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from scrypted_sdk import ScryptedInterface

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later

from .entity import (
    ScryptedDeviceEntity,
    ScryptedEntityDescriptionMixin,
    async_detection_classes,
    async_setup_scrypted_platform,
    device_matches,
    exposed_device,
)

# Seconds a detected sensor stays on after its class was last seen, matching
# the default of scrypted's own Smart Motion Sensor.
DETECTION_TIMEOUT = 60


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

    async def _discover(device_id: str) -> list[BinarySensorEntity]:
        entities: list[BinarySensorEntity] = [
            ScryptedBinarySensor(client, config_entry, device_id, description)
            for description in BINARY_SENSORS
            if device_matches(client, device_id, description.interface)
        ]
        if device_matches(client, device_id, ScryptedInterface.ObjectDetector.value):
            device = exposed_device(client, device_id)
            entities.extend(
                ScryptedObjectDetectedSensor(
                    client, config_entry, device_id, class_name
                )
                for class_name in await async_detection_classes(device)
            )
        return entities

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


class ScryptedObjectDetectedSensor(ScryptedDeviceEntity, BinarySensorEntity):
    """On while a camera keeps detecting one object class.

    scrypted reports detections as a stream with no end signal, so like its
    Smart Motion Sensor this turns off once DETECTION_TIMEOUT passes without
    another detection of the class. Created disabled: detection models can
    advertise dozens of classes, and a disabled sensor never subscribes.
    """

    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY
    _attr_entity_registry_enabled_default = False
    _attr_is_on = False

    def __init__(
        self,
        client,
        entry: ConfigEntry,
        device_id: str,
        class_name: str,
    ) -> None:
        """Initialize the sensor for one detection class."""
        super().__init__(
            client,
            entry,
            device_id,
            BinarySensorEntityDescription(
                key=f"{class_name}_detected",
                name=f"{class_name.capitalize()} detected",
            ),
        )
        self._class_name = class_name
        self._cancel_clear: CALLBACK_TYPE | None = None

    async def async_added_to_hass(self) -> None:
        """Receive the device's detections."""
        await super().async_added_to_hass()
        self._async_listen_detections(self._on_objects_detected)
        self.async_on_remove(self._async_cancel_clear)

    @callback
    def _on_objects_detected(self, data: dict) -> None:
        """Turn on, or extend the timeout, when the payload has this class."""
        if not any(
            detection.get("className") == self._class_name
            for detection in data.get("detections") or []
        ):
            return
        self._async_cancel_clear()
        self._cancel_clear = async_call_later(
            self.hass, DETECTION_TIMEOUT, self._async_clear
        )
        if not self._attr_is_on:
            self._attr_is_on = True
            self.async_write_ha_state()

    @callback
    def _async_clear(self, _now: datetime) -> None:
        self._cancel_clear = None
        self._attr_is_on = False
        self.async_write_ha_state()

    @callback
    def _async_cancel_clear(self) -> None:
        if self._cancel_clear:
            self._cancel_clear()
            self._cancel_clear = None
