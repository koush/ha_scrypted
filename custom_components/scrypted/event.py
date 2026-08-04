"""Event entities for stateless Scrypted events."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.event import (
    EventDeviceClass,
    EventEntity,
    EventEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from scrypted_sdk import ScryptedInterface

from .const import SIGNAL_CONNECTION
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
    """Detection classes the device can report, minus scrypted's motion class."""
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
        super().__init__(client, entry, device_id, description)
        self._attr_event_types: list[str] = event_types
        self._unregister = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._register_listener()
        # Re-register the server-side listener after reconnects.
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_CONNECTION.format(self.entry.entry_id),
                self._handle_reconnect,
            )
        )

    async def async_will_remove_from_hass(self) -> None:
        self._remove_listener()

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
    def _handle_reconnect(self, connected: bool) -> None:
        if connected:
            self._remove_listener()
            self._register_listener()
        self.async_write_ha_state()

    def _on_objects_detected(self, device, event_details: dict, data: Any) -> None:
        """Runs on the HA loop via the engine.io read task."""
        detections = (data or {}).get("detections") or []
        seen: set[str] = set()
        for detection in detections:
            class_name = detection.get("className")
            if not class_name or class_name == MOTION_CLASS or class_name in seen:
                continue
            seen.add(class_name)
            if class_name not in self._attr_event_types:
                # event_types is fixed at trigger time; extend for unknown classes
                self._attr_event_types = [*self._attr_event_types, class_name]
            self._trigger_event(
                class_name,
                {
                    "label": detection.get("label"),
                    "score": detection.get("score"),
                    "zones": detection.get("zones"),
                    "detection_id": (data or {}).get("detectionId"),
                },
            )
        if seen:
            self.async_write_ha_state()


class ScryptedDoorbellEvent(ScryptedDeviceEntity, EventEntity):
    """Fires on doorbell button presses (binaryState rising edge)."""

    _attr_event_types = ["ring"]

    @callback
    def _handle_device_update(self, event_details: dict, value: Any) -> None:
        if event_details.get("property") == "binaryState" and value:
            self._trigger_event("ring")
        self.async_write_ha_state()
