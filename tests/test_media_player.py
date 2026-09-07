"""Tests for scrypted intercom media players."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.exceptions import HomeAssistantError

from tests.conftest import setup_entry


async def test_intercom_media_player_created(
    hass, fake_sdk, enable_custom_integrations
):
    """Intercom media player created."""
    await setup_entry(hass)
    state = hass.states.get("media_player.doorbell_speaker")
    assert state is not None
    assert state.state == "idle"
    # cam1 has no Intercom interface -> no media player
    assert hass.states.get("media_player.porch_front_door_cam_speaker") is None


async def test_play_media_url_starts_intercom(
    hass, fake_sdk, enable_custom_integrations
):
    """Play media url starts intercom."""
    await setup_entry(hass)
    await hass.services.async_call(
        "media_player",
        "play_media",
        {
            "entity_id": "media_player.doorbell_speaker",
            "media_content_type": "music",
            "media_content_id": "http://example/announcement.mp3",
        },
        blocking=True,
    )
    fake_sdk.mediaManager.createMediaObjectFromUrl.assert_awaited_with(
        "http://example/announcement.mp3"
    )
    device = fake_sdk.systemManager.getDeviceById("bell1")
    device.startIntercom.assert_awaited()
    assert hass.states.get("media_player.doorbell_speaker").state == "playing"

    await hass.services.async_call(
        "media_player",
        "media_stop",
        {"entity_id": "media_player.doorbell_speaker"},
        blocking=True,
    )
    device.stopIntercom.assert_awaited()
    assert hass.states.get("media_player.doorbell_speaker").state == "idle"


async def test_play_media_resolves_media_source(
    hass, fake_sdk, enable_custom_integrations
):
    """Play media resolves media source."""
    await setup_entry(hass)
    resolved = SimpleNamespace(url="/local/tts.mp3", mime_type="audio/mpeg")
    with patch(
        "custom_components.scrypted.media_player.media_source.async_resolve_media",
        AsyncMock(return_value=resolved),
    ):
        await hass.services.async_call(
            "media_player",
            "play_media",
            {
                "entity_id": "media_player.doorbell_speaker",
                "media_content_type": "music",
                "media_content_id": "media-source://tts/cloud?message=hi",
                "announce": True,
            },
            blocking=True,
        )
    url = fake_sdk.mediaManager.createMediaObjectFromUrl.await_args.args[0]
    # relative URL is made absolute (and auth-signed) for the scrypted server
    assert "/local/tts.mp3" in url
    assert url.startswith("http")


async def test_play_media_unavailable_device_raises(
    hass, fake_sdk, enable_custom_integrations
):
    """Play media unavailable device raises."""
    await setup_entry(hass)
    component = hass.data["media_player"]
    entity = component.get_entity("media_player.doorbell_speaker")
    fake_sdk.systemManager.systemState.pop("bell1")
    with pytest.raises(HomeAssistantError):
        await entity.async_play_media("music", "http://example/x.mp3")
    # stop on missing device is a quiet no-op
    await entity.async_media_stop()


async def test_browse_media_delegates_to_media_source(
    hass, fake_sdk, enable_custom_integrations
):
    """Browse media delegates to media source."""
    await setup_entry(hass)
    sentinel = object()
    with patch(
        "custom_components.scrypted.media_player.media_source.async_browse_media",
        AsyncMock(return_value=sentinel),
    ) as browse:
        component = hass.data["media_player"]
        entity = component.get_entity("media_player.doorbell_speaker")
        result = await entity.async_browse_media(None, None)
    assert result is sentinel
    browse.assert_awaited()
