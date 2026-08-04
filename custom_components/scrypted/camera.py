"""Camera entities for Scrypted video devices.

Cameras are snapshot-only by design: live streaming is intentionally not
supported so that users view live video through the scrypted NVR cards
instead (upstream request).
"""
from __future__ import annotations

import logging

from homeassistant.components.camera import Camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .hub import ScryptedClient
from .entity import ScryptedDeviceEntity, async_setup_scrypted_platform, device_matches
from scrypted_sdk import ScryptedInterface

_LOGGER = logging.getLogger(__name__)

# A real EntityDescription so Entity internals (entity_registry_enabled_default,
# icon resolution, etc.) behave; cameras are not table-driven.
CAMERA_DESCRIPTION = EntityDescription(key="camera", name=None)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up scrypted cameras."""
    client = config_entry.runtime_data.client

    def _discover(device_id: str) -> list[ScryptedCamera]:
        if not device_matches(
            client, device_id, ScryptedInterface.VideoCamera.value
        ):
            return []
        return [ScryptedCamera(client, config_entry, device_id, CAMERA_DESCRIPTION)]

    await async_setup_scrypted_platform(
        hass, config_entry, async_add_entities, _discover
    )


class ScryptedCamera(ScryptedDeviceEntity, Camera):
    """A scrypted VideoCamera device, exposed snapshot-only."""

    _attr_name = None

    def __init__(
        self,
        client: ScryptedClient,
        entry: ConfigEntry,
        device_id: str,
        description: EntityDescription,
    ) -> None:
        Camera.__init__(self)
        ScryptedDeviceEntity.__init__(self, client, entry, device_id, description)
        # Exposed so users can cross-reference entities with scrypted NVR cards.
        self._attr_extra_state_attributes = {"device_id": device_id}

    @property
    def is_recording(self) -> bool:
        device = self.device
        if device is None:
            return False
        if ScryptedInterface.VideoRecorder.value in (device.interfaces or []):
            return bool(device.recordingActive)
        return False

    @property
    def motion_detection_enabled(self) -> bool:
        device = self.device
        return bool(
            device
            and ScryptedInterface.MotionSensor.value in (device.interfaces or [])
        )

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Snapshot via Camera.takePicture, falling back to the video stream."""
        device = self.device
        if device is None or not self.client.sdk:
            return None
        try:
            if ScryptedInterface.Camera.value in (device.interfaces or []):
                media_object = await device.takePicture()
            else:
                media_object = await device.getVideoStream()
            buffer = await self.client.sdk.mediaManager.convertMediaObjectToBuffer(
                media_object, "image/jpeg"
            )
        except Exception:  # noqa: BLE001 - snapshot failures must not blow up HA
            _LOGGER.exception("Failed to fetch snapshot for %s", self.entity_id)
            return None
        return bytes(buffer)
