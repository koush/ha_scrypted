"""Event entities for stateless Scrypted events."""

from __future__ import annotations

import logging
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

from .entity import ScryptedDeviceEntity, async_setup_scrypted_platform, device_matches

_LOGGER = logging.getLogger(__name__)

# scrypted reports motion as a detection class (its motion pipeline rides the
# ObjectDetector interface); HA already exposes that signal via the motion
# binary_sensor, so the event entity only handles classified objects.
MOTION_CLASS = "motion"

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
        device = client.sdk.systemManager.getDeviceById(device_id)
        if device is None:
            return entities
        if device_matches(client, device_id, ScryptedInterface.ObjectDetector.value):
            event_types = await _async_object_event_types(device)
            if event_types:
                entities.append(
                    ScryptedObjectDetectionEvent(
                        client, config_entry, device_id, OBJECT_DETECTED, event_types
                    )
                )
        if device.type == "Doorbell" and device_matches(
            client, device_id, ScryptedInterface.BinarySensor.value
        ):
            entities.append(
                ScryptedDoorbellEvent(client, config_entry, device_id, DOORBELL)
            )
        return entities

    await async_setup_scrypted_platform(
        hass, config_entry, async_add_entities, _discover
    )


async def _async_object_event_types(device) -> list[str]:
    """Return the detection classes the device reports, minus scrypted's motion class."""
    try:
        object_types = await device.getObjectTypes()
        classes = list((object_types or {}).get("classes") or [])
    except Exception:  # noqa: BLE001 - some detectors don't implement this
        _LOGGER.debug("getObjectTypes failed for %s", device.id, exc_info=True)
        classes = []
    return [name for name in classes if name != MOTION_CLASS]


class ScryptedObjectDetectionEvent(ScryptedDeviceEntity, EventEntity):
    """Fires when the scrypted ObjectDetector reports detections.

    Stateless ObjectsDetected payloads do not reach system listeners, so this
    entity owns a per-device server-side subscription (listenDevice) and must
    re-register it after every reconnect.
    """

    def __init__(self, client, entry, device_id, description, event_types) -> None:
        """Initialize the object detection event entity."""
        super().__init__(client, entry, device_id, description)
        self._attr_event_types: list[str] = event_types
        self._unregister = None

    async def async_added_to_hass(self) -> None:
        """Register the detection listener and re-register it after reconnects."""
        await super().async_added_to_hass()
        self._register_listener()
        self.async_on_remove(self._remove_listener)

    def _register_listener(self) -> None:
        if not self.client.sdk:
            return
        self._unregister = self.client.sdk.systemManager.listenDevice(
            self.device_id,
            ScryptedInterface.ObjectDetector.value,
            self._on_objects_detected,
        )

    def _remove_listener(self) -> None:
        if self._unregister:
            self._unregister.removeListener()
            self._unregister = None

    @callback
    def _handle_connection_change(self, connected: bool) -> None:
        if connected:
            # The previous registration died with the old transport; calling
            # removeListener on it would RPC over a closed peer.
            self._unregister = None
            self._register_listener()
        super()._handle_connection_change(connected)

    def _on_objects_detected(self, device, event_details: dict, data: Any) -> None:
        """Fire one event per detected class; runs on the HA loop via the engine.io read task."""
        data = data or {}
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
