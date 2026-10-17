"""Camera entities for Scrypted video devices.

Cameras are snapshot-only by design: live streaming is intentionally not
supported so that users view live video through the scrypted NVR cards
instead (upstream request).
"""

from __future__ import annotations

import logging

from scrypted_sdk import ScryptedInterface

from homeassistant.components.camera import CAMERA_IMAGE_TIMEOUT, Camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import ScryptedDeviceEntity, async_setup_scrypted_platform, device_matches
from .hub import ScryptedClient

_LOGGER = logging.getLogger(__name__)

# A real EntityDescription so Entity internals (entity_registry_enabled_default,
# icon resolution, etc.) behave; cameras are not table-driven.
CAMERA_DESCRIPTION = EntityDescription(key="camera", name=None)

# How long scrypted may spend capturing a fresh frame. It must finish inside
# Home Assistant's own image timeout, with room left for the RPC round trip and
# the JPEG conversion; if both sides waited the full timeout they would race.
FRESH_PICTURE_TIMEOUT_MS = (CAMERA_IMAGE_TIMEOUT - 2) * 1000


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up scrypted cameras."""
    client = config_entry.runtime_data.client

    def _discover(device_id: str) -> list[ScryptedCamera]:
        if not device_matches(client, device_id, ScryptedInterface.VideoCamera.value):
            return []
        return [ScryptedCamera(client, config_entry, device_id, CAMERA_DESCRIPTION)]

    await async_setup_scrypted_platform(
        hass, config_entry, async_add_entities, _discover
    )


def _picture_size_hint(width: int | None, height: int | None) -> dict[str, int] | None:
    """Return the takePicture size hint for an HA image request.

    Returns None when HA asked for no size (a full-resolution capture).
    HA passes width/height as a best-effort minimum and downscales whatever
    comes back while preserving aspect ratio. scrypted stretches the image to
    fit when given both dimensions, so the hint must name at most one.
    """
    # Width is what dashboard cards size by. Low-resolution cameras can come
    # back slightly larger than native after re-encoding; skipping the hint
    # would need the native size, which only an unsized snapshot reveals.
    if width is not None:
        return {"width": width}
    if height is not None:
        return {"height": height}
    return None


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
        """Initialize the camera entity."""
        Camera.__init__(self)
        ScryptedDeviceEntity.__init__(self, client, entry, device_id, description)
        # Exposed so users can cross-reference entities with scrypted NVR cards.
        self._attr_extra_state_attributes = {"device_id": device_id}

    @property
    def is_recording(self) -> bool:
        """Return True when the device reports an active recording."""
        device = self.device
        if device is None:
            return False
        if ScryptedInterface.VideoRecorder.value in (device.interfaces or []):
            return bool(device.recordingActive)
        return False

    @property
    def motion_detection_enabled(self) -> bool:
        """Return True when the device exposes a motion sensor."""
        device = self.device
        return bool(
            device and ScryptedInterface.MotionSensor.value in (device.interfaces or [])
        )

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Snapshot via Camera.takePicture, falling back to the video stream.

        Home Assistant passes dimensions for thumbnail refreshes, where a
        recent image is fine. Those are flagged periodic: scrypted's snapshot
        plugin then accepts a capture up to 20s old and waits at most 3s for a
        fresh one, instead of up to 10s, which would race Home Assistant's own
        image timeout. They also carry a size hint so scrypted returns a
        thumbnail rather than the full frame. A request without dimensions,
        such as the camera.snapshot service, wants the frame as of now, so it
        asks for an event capture: never shared, never served from cache.
        """
        device = self.device
        if device is None or not self.client.sdk:
            return None
        try:
            if ScryptedInterface.Camera.value in (device.interfaces or []):
                hint = _picture_size_hint(width, height)
                if hint is None:
                    media_object = await device.takePicture(
                        {"reason": "event", "timeout": FRESH_PICTURE_TIMEOUT_MS}
                    )
                else:
                    # Resizing in scrypted also re-encodes, which drops the
                    # malformed COM segments some camera firmware (Dahua/Amcrest)
                    # writes; HA's turbojpeg downscale logs those as corrupt.
                    media_object = await device.takePicture(
                        {"picture": hint, "reason": "periodic", "periodicRequest": True}
                    )
            else:
                media_object = await device.getVideoStream()
            buffer = await self.client.sdk.mediaManager.convertMediaObjectToBuffer(
                media_object, "image/jpeg"
            )
        except Exception:  # noqa: BLE001 - snapshot failures must not blow up HA
            _LOGGER.exception("Failed to fetch snapshot for %s", self.entity_id)
            return None
        return bytes(buffer)
