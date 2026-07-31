"""Media source exposing scrypted NVR detection clips."""
from __future__ import annotations

import logging
from datetime import timedelta

from yarl import URL

from homeassistant.components.camera import DynamicStreamSettings
from homeassistant.components.media_player import BrowseError, MediaClass
from homeassistant.components.media_source import (
    BrowseMediaSource,
    MediaSource,
    MediaSourceItem,
    PlayMedia,
    Unresolvable,
)
from homeassistant.components.stream import FORMAT_CONTENT_TYPE, HLS_PROVIDER, create_stream
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .entity import device_matches
from scrypted_sdk.scrypted_python.scrypted_sdk.types import ScryptedInterface, ScryptedMimeTypes

_LOGGER = logging.getLogger(__name__)

DAYS_SHOWN = 7
DAY_FORMAT = "%Y-%m-%d"


async def async_get_media_source(hass: HomeAssistant) -> ScryptedMediaSource:
    """Set up the scrypted media source."""
    return ScryptedMediaSource(hass)


def _loaded_entries(hass: HomeAssistant) -> list[ConfigEntry]:
    return [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
        and entry.runtime_data.client is not None
    ]


def _entry_token(hass: HomeAssistant, entry_id: str) -> str:
    """Ingress token for a loaded entry (async_setup_entry registers it before load completes)."""
    token = next(
        (
            token
            for token, entry in hass.data[DOMAIN].items()
            if entry.entry_id == entry_id
        ),
        None,
    )
    if token is None:
        raise BrowseError(f"Scrypted entry {entry_id} has no ingress token")
    return token


def _proxy_url(token: str, href: str) -> str:
    """Rewrite a scrypted href to the integration's streaming proxy."""
    path_qs = URL(href).raw_path_qs
    return f"/api/scrypted/{token}/{path_qs.lstrip('/')}"


def _clip_title(clip: dict) -> str:
    started = dt_util.as_local(
        dt_util.utc_from_timestamp(clip["startTime"] / 1000)
    )
    title = started.strftime("%I:%M:%S %p").lstrip("0")
    classes = ", ".join(clip.get("detectionClasses") or [])
    return f"{title} — {classes}" if classes else title


def _resource_href(clip: dict, kind: str) -> str | None:
    return ((clip.get("resources") or {}).get(kind) or {}).get("href")


class ScryptedMediaSource(MediaSource):
    """Browse scrypted NVR detection clips by camera and day."""

    name = "Scrypted NVR"

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(DOMAIN)
        self.hass = hass

    async def async_browse_media(self, item: MediaSourceItem) -> BrowseMediaSource:
        # scrypted device/clip ids are internally generated and never contain
        # "/", so a bounded split is safe here.
        parts = (item.identifier or "").split("/", 2) if item.identifier else []
        if not parts:
            return self._browse_root()
        entry = self._get_entry(parts[0])
        if len(parts) == 1:
            return self._browse_entry(entry)
        if len(parts) == 2:
            return self._browse_camera(entry, parts[1])
        return await self._browse_day(entry, parts[1], parts[2])

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        # scrypted device/clip ids are internally generated and never contain
        # "/"; a violating clip id just fails the lookup below as Unresolvable.
        parts = (item.identifier or "").split("/", 3)
        if len(parts) != 4:
            raise Unresolvable(f"Invalid clip identifier: {item.identifier}")
        entry_id, device_id, day_id, clip_id = parts
        entry = self._get_entry(entry_id, error_cls=Unresolvable)
        clips = await self._day_clips(entry, device_id, day_id)
        clip = next((c for c in clips if c.get("id") == clip_id), None)
        if clip is None:
            raise Unresolvable(f"Clip {clip_id} not found")
        token = _entry_token(self.hass, entry_id)
        href = _resource_href(clip, "video")
        if href is not None:
            return PlayMedia(_proxy_url(token, href), "video/mp4")
        client = entry.runtime_data.client
        device = client.sdk.systemManager.getDeviceById(device_id)
        media_object = await device.getVideoClip(clip["videoId"])
        ffmpeg_input = await client.sdk.mediaManager.convertMediaObjectToJSON(
            media_object, ScryptedMimeTypes.FFmpegInput.value
        )
        urls = ffmpeg_input.get("urls") or []
        rtsp_url = next(iter(urls), None) or ffmpeg_input.get("url")
        if not rtsp_url:
            raise Unresolvable(f"Clip {clip_id} has no playable stream")
        return await self._async_hls_play_media(rtsp_url)

    async def _async_hls_play_media(self, rtsp_url: str) -> PlayMedia:
        """Expose an RTSP clip session as browser-playable HLS via HA's stream component."""
        # scrypted's clip RTSP sessions are TCP; without this PyAV defaults to
        # UDP and fails with "Invalid data found when processing input".
        stream = create_stream(
            self.hass,
            rtsp_url,
            options={"rtsp_transport": "tcp"},
            dynamic_stream_settings=DynamicStreamSettings(),
        )
        stream.add_provider(HLS_PROVIDER)
        await stream.start()
        return PlayMedia(
            stream.endpoint_url(HLS_PROVIDER), FORMAT_CONTENT_TYPE[HLS_PROVIDER]
        )

    def _get_entry(
        self, entry_id: str, error_cls: type[Exception] = BrowseError
    ) -> ConfigEntry:
        for entry in _loaded_entries(self.hass):
            if entry.entry_id == entry_id:
                if entry.runtime_data.client.sdk is None:
                    raise error_cls(f"Scrypted {entry.title} is disconnected")
                return entry
        raise error_cls(f"Scrypted entry {entry_id} is not loaded")

    def _browse_root(self) -> BrowseMediaSource:
        entries = _loaded_entries(self.hass)
        if len(entries) == 1 and entries[0].runtime_data.client.sdk is not None:
            return self._browse_entry(entries[0], as_root=True)
        return self._node(
            identifier="",
            title="Scrypted NVR",
            children=[
                self._node(identifier=entry.entry_id, title=entry.title)
                for entry in entries
            ],
        )

    def _browse_entry(self, entry: ConfigEntry, as_root: bool = False) -> BrowseMediaSource:
        client = entry.runtime_data.client
        children = [
            self._node(
                identifier=f"{entry.entry_id}/{device_id}",
                title=client.sdk.systemManager.getDeviceById(device_id).name,
            )
            for device_id in client.device_ids
            if device_matches(
                client, device_id, ScryptedInterface.VideoClips.value
            )
        ]
        return self._node(
            identifier="" if as_root else entry.entry_id,
            title=entry.title,
            children=children,
        )

    def _browse_camera(self, entry: ConfigEntry, device_id: str) -> BrowseMediaSource:
        client = entry.runtime_data.client
        if not device_matches(client, device_id, ScryptedInterface.VideoClips.value):
            raise BrowseError(f"Unknown scrypted camera {device_id}")
        device = client.sdk.systemManager.getDeviceById(device_id)
        today = dt_util.start_of_local_day()
        children = []
        for offset in range(DAYS_SHOWN):
            day = today - timedelta(days=offset)
            if offset == 0:
                title = "Today"
            elif offset == 1:
                title = "Yesterday"
            else:
                title = f"{day:%A, %b} {day.day}"
            children.append(
                self._node(
                    identifier=(
                        f"{entry.entry_id}/{device_id}/{day.strftime(DAY_FORMAT)}"
                    ),
                    title=title,
                )
            )
        return self._node(
            identifier=f"{entry.entry_id}/{device_id}",
            title=device.name,
            children=children,
        )

    async def _browse_day(
        self, entry: ConfigEntry, device_id: str, day_id: str
    ) -> BrowseMediaSource:
        clips = await self._day_clips(entry, device_id, day_id)
        token = _entry_token(self.hass, entry.entry_id)
        children = []
        for clip in sorted(
            (c for c in clips if c.get("startTime") is not None and c.get("id")),
            key=lambda c: c["startTime"],
            reverse=True,
        ):
            thumbnail_href = _resource_href(clip, "thumbnail")
            children.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"{entry.entry_id}/{device_id}/{day_id}/{clip['id']}",
                    media_class=MediaClass.VIDEO,
                    media_content_type="video/mp4",
                    title=_clip_title(clip),
                    can_play=True,
                    can_expand=False,
                    thumbnail=(
                        _proxy_url(token, thumbnail_href) if thumbnail_href else None
                    ),
                )
            )
        return self._node(
            identifier=f"{entry.entry_id}/{device_id}/{day_id}",
            title=day_id,
            children=children,
            children_media_class=MediaClass.VIDEO,
        )

    async def _day_clips(
        self, entry: ConfigEntry, device_id: str, day_id: str
    ) -> list[dict]:
        client = entry.runtime_data.client
        if not device_matches(client, device_id, ScryptedInterface.VideoClips.value):
            raise BrowseError(f"Unknown scrypted camera {device_id}")
        device = client.sdk.systemManager.getDeviceById(device_id)
        day = dt_util.parse_date(day_id)
        if day is None:
            raise BrowseError(f"Invalid day {day_id}")
        start = dt_util.start_of_local_day(day)
        end = dt_util.start_of_local_day(day + timedelta(days=1))
        start_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)
        try:
            return await device.getVideoClips(
                {"startTime": start_ms, "endTime": end_ms}
            ) or []
        except Exception as err:  # noqa: BLE001 - RPC failures surface in the UI
            _LOGGER.debug("getVideoClips failed for %s", device_id, exc_info=True)
            raise BrowseError(f"Could not load clips for {device.name}") from err

    def _node(
        self,
        identifier: str,
        title: str,
        children: list[BrowseMediaSource] | None = None,
        children_media_class: MediaClass = MediaClass.DIRECTORY,
    ) -> BrowseMediaSource:
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=identifier,
            media_class=MediaClass.DIRECTORY,
            media_content_type="",
            title=title,
            can_play=False,
            can_expand=True,
            children=children,
            children_media_class=children_media_class,
        )
