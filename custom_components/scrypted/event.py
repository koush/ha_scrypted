"""Event entities for stateless Scrypted events."""

from __future__ import annotations

from typing import Any

from scrypted_sdk import ScryptedInterface

from homeassistant.components.event import (
    EventDeviceClass,
    EventEntity,
    EventEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import (
    MOTION_CLASS,
    ScryptedDeviceEntity,
    async_detection_classes,
    async_setup_scrypted_platform,
    exposed_device,
)

OBJECT_DETECTED = EventEntityDescription(
    key="object_detected",
    name="Object detected",
    device_class=EventDeviceClass.MOTION,
)
DOORBELL = EventEntityDescription(
    key="doorbell",
    name="Doorbell",
    device_class=EventDeviceClass.DOORBELL,
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up scrypted event entities."""
    client = config_entry.runtime_data.client

    async def _discover(device_id: str) -> list[EventEntity]:
        entities: list[EventEntity] = []
        device = exposed_device(client, device_id)
        if device is None:
            return entities
        interfaces = device.interfaces or []
        if ScryptedInterface.ObjectDetector.value in interfaces:
            event_types = await async_detection_classes(device)
            if event_types:
                entities.append(
                    ScryptedObjectDetectionEvent(
                        client, config_entry, device_id, OBJECT_DETECTED, event_types
                    )
                )
        if (
            device.type == "Doorbell"
            and ScryptedInterface.BinarySensor.value in interfaces
        ):
            entities.append(
                ScryptedDoorbellEvent(client, config_entry, device_id, DOORBELL)
            )
        return entities

    await async_setup_scrypted_platform(
        hass, config_entry, async_add_entities, _discover
    )


class ScryptedObjectDetectionEvent(ScryptedDeviceEntity, EventEntity):
    """Fires when the scrypted ObjectDetector reports detections."""

    def __init__(self, client, entry, device_id, description, event_types) -> None:
        """Initialize the object detection event entity."""
        super().__init__(client, entry, device_id, description)
        self._attr_event_types: list[str] = event_types

    async def async_added_to_hass(self) -> None:
        """Receive the device's detections."""
        await super().async_added_to_hass()
        self._async_listen_detections(self._on_objects_detected)

    @callback
    def _on_objects_detected(self, data: dict) -> None:
        """Fire one event per detected class."""
        detection_id = data.get("detectionId")
        seen: set[str] = set()
        for detection in data.get("detections") or []:
            class_name = detection.get("className")
            if not class_name or class_name == MOTION_CLASS or class_name in seen:
                continue
            seen.add(class_name)
            if class_name not in self._attr_event_types:
                # _trigger_event rejects types outside event_types; learn classes
                # the detector did not advertise up front.
                self._attr_event_types = [*self._attr_event_types, class_name]
            self._trigger_event(
                class_name,
                {
                    "label": detection.get("label"),
                    "score": detection.get("score"),
                    "zones": detection.get("zones"),
                    "detection_id": detection_id,
                },
            )
            # EventEntity keeps only the last event, so write per class rather
            # than once per payload; HA forces strictly increasing timestamps.
            self.async_write_ha_state()


class ScryptedDoorbellEvent(ScryptedDeviceEntity, EventEntity):
    """Fires on doorbell button presses (binaryState rising edge)."""

    _attr_event_types = ["ring"]

    @callback
    def _handle_device_update(self, event_details: dict, value: Any) -> None:
        if event_details.get("property") == "binaryState" and value:
            self._trigger_event("ring")
        self.async_write_ha_state()
