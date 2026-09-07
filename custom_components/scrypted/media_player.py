"""Media player entities for Scrypted intercom-capable devices.

Camera entities are snapshot-only (live view happens in the Scrypted NVR
cards), so two-way audio is exposed the HA-native way instead: each scrypted
Intercom device becomes a speaker media_player that plays URLs/TTS through the
camera or doorbell speaker.
"""

from __future__ import annotations

import logging
from typing import Any

from scrypted_sdk import ScryptedInterface

from homeassistant.components import media_source
from homeassistant.components.media_player import (
    BrowseMedia,
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    async_process_play_media_url,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import ScryptedDeviceEntity, async_setup_scrypted_platform, device_matches

_LOGGER = logging.getLogger(__name__)

SPEAKER_DESCRIPTION = EntityDescription(key="speaker", name="Speaker")


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up scrypted intercom media players."""
    client = config_entry.runtime_data.client

    def _discover(device_id: str) -> list[ScryptedIntercom]:
        if not device_matches(client, device_id, ScryptedInterface.Intercom.value):
            return []
        return [ScryptedIntercom(client, config_entry, device_id, SPEAKER_DESCRIPTION)]

    await async_setup_scrypted_platform(
        hass, config_entry, async_add_entities, _discover
    )


class ScryptedIntercom(ScryptedDeviceEntity, MediaPlayerEntity):
    """Plays audio through a scrypted Intercom device's speaker."""

    _attr_device_class = MediaPlayerDeviceClass.SPEAKER
    _attr_supported_features = (
        MediaPlayerEntityFeature.PLAY_MEDIA
        | MediaPlayerEntityFeature.STOP
        | MediaPlayerEntityFeature.MEDIA_ANNOUNCE
        | MediaPlayerEntityFeature.BROWSE_MEDIA
    )
    _attr_state = MediaPlayerState.IDLE

    async def async_play_media(
        self,
        media_type: str,
        media_id: str,
        announce: bool | None = None,
        **kwargs: Any,
    ) -> None:
        """Resolve the media to a URL and play it through the intercom."""
        device = self.device
        if device is None or not self.client.sdk:
            raise HomeAssistantError(
                f"Scrypted device for {self.entity_id} is unavailable"
            )
        if media_source.is_media_source_id(media_id):
            play_item = await media_source.async_resolve_media(
                self.hass, media_id, self.entity_id
            )
            media_id = play_item.url
        # The scrypted server fetches the URL itself, so it must be absolute.
        media_id = async_process_play_media_url(self.hass, media_id)
        media_object = await self.client.sdk.mediaManager.createMediaObjectFromUrl(
            media_id
        )
        await device.startIntercom(media_object)
        self._attr_state = MediaPlayerState.PLAYING
        self.async_write_ha_state()

    async def async_media_stop(self) -> None:
        """Stop intercom playback."""
        device = self.device
        if device is not None:
            await device.stopIntercom()
        self._attr_state = MediaPlayerState.IDLE
        self.async_write_ha_state()

    async def async_browse_media(
        self, media_content_type: str | None = None, media_content_id: str | None = None
    ) -> BrowseMedia:
        """Browse audio from media sources (local media, TTS, etc.)."""
        return await media_source.async_browse_media(
            self.hass,
            media_content_id,
            content_filter=lambda item: item.media_content_type.startswith("audio/"),
        )
