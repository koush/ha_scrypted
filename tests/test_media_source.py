"""Tests for the scrypted NVR clips media source."""
from unittest.mock import AsyncMock, Mock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.components import media_source
from homeassistant.components.media_player import BrowseError
from homeassistant.components.stream import FORMAT_CONTENT_TYPE, HLS_PROVIDER
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

import custom_components.scrypted as scrypted
from custom_components.scrypted.const import (
    CONF_AUTO_REGISTER_RESOURCES,
    CONF_DEVICE_TYPES,
    CONF_ENABLE_ENTITIES,
    CONF_SCRYPTED_NVR,
    DOMAIN,
)
from custom_components.scrypted.media_source import _entry_token
from tests.conftest import video_clip
from tests.test_binary_sensor import setup_entry


def today_ms(hour=15, minute=42, second=7):
    """Epoch millis for a time within today's local day."""
    now = dt_util.now()
    stamp = now.replace(hour=hour, minute=minute, second=second, microsecond=0)
    return int(stamp.timestamp() * 1000)


async def setup_media_source(hass):
    entry = await setup_entry(hass)
    assert await async_setup_component(hass, "media_source", {})
    return entry


async def test_browse_root_lists_eligible_cameras(hass, fake_sdk, enable_custom_integrations):
    await setup_media_source(hass)
    root = await media_source.async_browse_media(hass, "media-source://scrypted")
    titles = [child.title for child in root.children]
    # cam1 has VideoClips; bell1/haimport1/others do not (or are excluded)
    assert titles == ["Front Door Cam"]
    assert root.children[0].can_expand and not root.children[0].can_play


async def test_browse_camera_lists_seven_days(hass, fake_sdk, enable_custom_integrations):
    entry = await setup_media_source(hass)
    camera = await media_source.async_browse_media(
        hass, f"media-source://scrypted/{entry.entry_id}/cam1"
    )
    assert len(camera.children) == 7
    assert camera.children[0].title == "Today"
    assert camera.children[1].title == "Yesterday"


async def test_browse_day_lists_clips_with_one_rpc(hass, fake_sdk, enable_custom_integrations):
    entry = await setup_media_source(hass)
    device = fake_sdk.systemManager.getDeviceById("cam1")
    device.getVideoClips.return_value = [
        video_clip("clip1", today_ms(15, 42, 7), detection_classes=["person", "motion"]),
        video_clip("clip2", today_ms(9, 5, 0), detection_classes=[]),
    ]
    day_id = dt_util.now().strftime("%Y-%m-%d")
    day = await media_source.async_browse_media(
        hass, f"media-source://scrypted/{entry.entry_id}/cam1/{day_id}"
    )

    device.getVideoClips.assert_awaited_once()
    window = device.getVideoClips.await_args.args[0]
    start = dt_util.start_of_local_day()
    assert window["startTime"] == int(start.timestamp() * 1000)
    assert window["endTime"] == window["startTime"] + 24 * 3600 * 1000

    assert [c.title for c in day.children] == [
        "3:42:07 PM — person, motion",
        "9:05:00 AM",
    ]
    clip = day.children[0]
    assert clip.can_play and not clip.can_expand
    assert clip.thumbnail == "/api/scrypted/token/endpoint/@scrypted/nvr/public/clip1.jpg"


async def test_day_window_spans_dst_transition(hass, fake_sdk, enable_custom_integrations):
    """Fall-back day in America/New_York is 25 hours; the window must cover all of it."""
    await hass.config.async_set_time_zone("America/New_York")
    entry = await setup_media_source(hass)
    device = fake_sdk.systemManager.getDeviceById("cam1")

    await media_source.async_browse_media(
        hass, f"media-source://scrypted/{entry.entry_id}/cam1/2026-11-01"
    )
    window = device.getVideoClips.await_args.args[0]
    assert window["endTime"] - window["startTime"] == 25 * 3600 * 1000


async def test_resolve_clip_with_resources(hass, fake_sdk, enable_custom_integrations):
    entry = await setup_media_source(hass)
    device = fake_sdk.systemManager.getDeviceById("cam1")
    device.getVideoClips.return_value = [video_clip("clip1", today_ms())]
    day_id = dt_util.now().strftime("%Y-%m-%d")

    play = await media_source.async_resolve_media(
        hass, f"media-source://scrypted/{entry.entry_id}/cam1/{day_id}/clip1", None
    )
    assert play.url == "/api/scrypted/token/endpoint/@scrypted/nvr/public/clip1.mp4"
    assert play.mime_type == "video/mp4"


async def test_resolve_clip_without_resources_falls_back(
    hass, fake_sdk, enable_custom_integrations
):
    entry = await setup_media_source(hass)
    device = fake_sdk.systemManager.getDeviceById("cam1")
    device.getVideoClips.return_value = [
        video_clip("clip1", today_ms(), with_resources=False)
    ]
    day_id = dt_util.now().strftime("%Y-%m-%d")

    fake_sdk.mediaManager.convertMediaObjectToJSON.return_value = {
        "url": "rtsp://127.0.0.1:1/x",
        "urls": ["rtsp://192.168.0.9:1/x"],
    }

    fake_stream = Mock()
    fake_stream.add_provider = Mock()
    fake_stream.start = AsyncMock()
    fake_stream.endpoint_url = Mock(
        return_value="/api/hls/xyz/master_playlist.m3u8"
    )
    create_stream_mock = Mock(return_value=fake_stream)
    with patch(
        "custom_components.scrypted.media_source.create_stream", create_stream_mock
    ):
        play = await media_source.async_resolve_media(
            hass, f"media-source://scrypted/{entry.entry_id}/cam1/{day_id}/clip1", None
        )

    device.getVideoClip.assert_awaited_once_with("clip1")
    fake_sdk.mediaManager.convertMediaObjectToJSON.assert_awaited_once()
    assert (
        fake_sdk.mediaManager.convertMediaObjectToJSON.await_args.args[1]
        == "x-scrypted/x-ffmpeg-input"
    )
    assert create_stream_mock.call_args.args[1] == "rtsp://192.168.0.9:1/x"
    fake_stream.add_provider.assert_called_once_with(HLS_PROVIDER)
    fake_stream.start.assert_awaited_once()
    assert play.url == "/api/hls/xyz/master_playlist.m3u8"
    assert play.mime_type == FORMAT_CONTENT_TYPE[HLS_PROVIDER]


async def test_resolve_clip_ffmpeg_input_without_urls_unresolvable(
    hass, fake_sdk, enable_custom_integrations
):
    entry = await setup_media_source(hass)
    device = fake_sdk.systemManager.getDeviceById("cam1")
    device.getVideoClips.return_value = [
        video_clip("clip1", today_ms(), with_resources=False)
    ]
    day_id = dt_util.now().strftime("%Y-%m-%d")

    fake_sdk.mediaManager.convertMediaObjectToJSON.return_value = {"container": "rtsp"}

    with pytest.raises(media_source.Unresolvable, match="clip1"):
        await media_source.async_resolve_media(
            hass, f"media-source://scrypted/{entry.entry_id}/cam1/{day_id}/clip1", None
        )


async def test_resolve_unknown_clip_unresolvable(hass, fake_sdk, enable_custom_integrations):
    entry = await setup_media_source(hass)
    day_id = dt_util.now().strftime("%Y-%m-%d")
    with pytest.raises(media_source.Unresolvable, match="ghost"):
        await media_source.async_resolve_media(
            hass, f"media-source://scrypted/{entry.entry_id}/cam1/{day_id}/ghost", None
        )


async def test_browse_errors(hass, fake_sdk, enable_custom_integrations):
    entry = await setup_media_source(hass)
    device = fake_sdk.systemManager.getDeviceById("cam1")
    day_id = dt_util.now().strftime("%Y-%m-%d")

    # RPC failure surfaces as BrowseError
    device.getVideoClips.side_effect = RuntimeError("boom")
    with pytest.raises(BrowseError):
        await media_source.async_browse_media(
            hass, f"media-source://scrypted/{entry.entry_id}/cam1/{day_id}"
        )

    # unknown device
    with pytest.raises(BrowseError):
        await media_source.async_browse_media(
            hass, f"media-source://scrypted/{entry.entry_id}/nope"
        )

    # disconnected client
    entry.runtime_data.client.sdk = None
    with pytest.raises(BrowseError):
        await media_source.async_browse_media(
            hass, f"media-source://scrypted/{entry.entry_id}/cam1"
        )
    entry.runtime_data.client.sdk = fake_sdk


async def test_malformed_clip_skipped(hass, fake_sdk, enable_custom_integrations):
    entry = await setup_media_source(hass)
    device = fake_sdk.systemManager.getDeviceById("cam1")
    good = video_clip("ok", today_ms())
    bad = video_clip("bad", today_ms())
    del bad["startTime"]
    device.getVideoClips.return_value = [good, bad]
    day_id = dt_util.now().strftime("%Y-%m-%d")
    day = await media_source.async_browse_media(
        hass, f"media-source://scrypted/{entry.entry_id}/cam1/{day_id}"
    )
    assert [c.identifier.rsplit("/", 1)[-1] for c in day.children] == ["ok"]


async def test_browse_unknown_device_within_day(hass, fake_sdk, enable_custom_integrations):
    entry = await setup_media_source(hass)
    day_id = dt_util.now().strftime("%Y-%m-%d")
    with pytest.raises(BrowseError):
        await media_source.async_browse_media(
            hass, f"media-source://scrypted/{entry.entry_id}/nope/{day_id}"
        )


async def test_browse_invalid_day(hass, fake_sdk, enable_custom_integrations):
    entry = await setup_media_source(hass)
    with pytest.raises(BrowseError):
        await media_source.async_browse_media(
            hass, f"media-source://scrypted/{entry.entry_id}/cam1/not-a-day"
        )


async def test_browse_unknown_entry(hass, fake_sdk, enable_custom_integrations):
    await setup_media_source(hass)
    with pytest.raises(BrowseError):
        await media_source.async_browse_media(hass, "media-source://scrypted/ghost-entry")


async def test_resolve_malformed_identifier(hass, fake_sdk, enable_custom_integrations):
    entry = await setup_media_source(hass)
    with pytest.raises(media_source.Unresolvable):
        await media_source.async_resolve_media(
            hass, f"media-source://scrypted/{entry.entry_id}/cam1", None
        )


async def test_entry_token_missing_raises_browse_error(
    hass, fake_sdk, enable_custom_integrations
):
    await setup_media_source(hass)
    with pytest.raises(BrowseError, match="missing"):
        _entry_token(hass, "missing")


async def test_browse_root_with_multiple_entries_lists_entries(
    hass, fake_sdk, enable_custom_integrations
):
    entry1 = await setup_media_source(hass)

    async def _fake_retrieve(data, session):
        return "token2"

    entry2 = MockConfigEntry(
        domain=DOMAIN,
        data={
            "host": "5.6.7.8",
            "username": "u2",
            "password": "p2",
            "name": "Scrypted 2",
            "icon": "mdi:memory",
        },
        options={
            CONF_AUTO_REGISTER_RESOURCES: False,
            CONF_SCRYPTED_NVR: False,
            CONF_ENABLE_ENTITIES: True,
            CONF_DEVICE_TYPES: ["Camera", "Doorbell", "Sensor"],
        },
    )
    entry2.add_to_hass(hass)
    with patch.object(scrypted, "retrieve_token", _fake_retrieve):
        assert await hass.config_entries.async_setup(entry2.entry_id)
        await hass.async_block_till_done()

    root = await media_source.async_browse_media(hass, "media-source://scrypted")
    titles = {child.title for child in root.children}
    assert titles == {entry1.title, entry2.title}

    camera = await media_source.async_browse_media(
        hass, f"media-source://scrypted/{entry1.entry_id}"
    )
    assert [child.title for child in camera.children] == ["Front Door Cam"]
