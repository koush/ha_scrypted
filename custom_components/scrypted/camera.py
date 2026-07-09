"""Camera entities for Scrypted video devices."""
from __future__ import annotations

import logging

from yarl import URL

from webrtc_models import RTCIceCandidateInit, RTCIceServer

from homeassistant.components.camera import (
    Camera,
    CameraEntityFeature,
    WebRTCClientConfiguration,
    WebRTCError,
    WebRTCSendMessage,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import ScryptedClient
from .entity import ScryptedDeviceEntity, async_setup_scrypted_platform, device_matches
from .sdk_compat import ScryptedInterface, ScryptedMimeTypes
from .webrtc import HomeAssistantSignalingSession

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
        device = client.sdk.systemManager.getDeviceById(device_id)
        camera_cls = (
            ScryptedWebRTCCamera
            if ScryptedInterface.RTCSignalingChannel.value in (device.interfaces or [])
            else ScryptedCamera
        )
        return [camera_cls(client, config_entry, device_id, CAMERA_DESCRIPTION)]

    await async_setup_scrypted_platform(
        hass, config_entry, async_add_entities, _discover
    )


class ScryptedCamera(ScryptedDeviceEntity, Camera):
    """A scrypted VideoCamera device."""

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
        self._attr_supported_features = CameraEntityFeature.STREAM

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

    async def stream_source(self) -> str | None:
        """RTSP URL from scrypted's rebroadcast (FFmpegInput)."""
        device = self.device
        if device is None or not self.client.sdk:
            return None
        try:
            media_object = await device.getVideoStream()
            ffmpeg_input = await self.client.sdk.mediaManager.convertMediaObjectToJSON(
                media_object, ScryptedMimeTypes.FFmpegInput.value
            )
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Failed to resolve stream for %s", self.entity_id)
            return None
        url = (ffmpeg_input or {}).get("url")
        if not url or not url.startswith("rtsp"):
            _LOGGER.debug(
                "No usable RTSP url for %s (got %s); install/enable the "
                "scrypted rebroadcast plugin",
                self.entity_id,
                url,
            )
            return None
        return self._rewrite_stream_host(url)

    def _rewrite_stream_host(self, url: str) -> str:
        """Rebroadcast URLs are server-local; swap in the configured host."""
        parsed = URL(url)
        if parsed.host in ("localhost", "127.0.0.1", "0.0.0.0"):
            host_ip = self.client.host.split(":")[0]
            return str(parsed.with_host(host_ip))
        return url


class ScryptedWebRTCCamera(ScryptedCamera):
    """A scrypted camera streamed natively over WebRTC.

    Overriding async_handle_async_webrtc_offer marks this class as a native
    WebRTC camera to Home Assistant, so it is only used for devices that
    implement RTCSignalingChannel; other cameras keep the RTSP path.
    """

    def __init__(self, *args) -> None:
        super().__init__(*args)
        self._webrtc_sessions: dict[str, HomeAssistantSignalingSession] = {}
        self._cached_ice_servers: list[RTCIceServer] | None = None

    def _async_get_webrtc_client_configuration(self) -> WebRTCClientConfiguration:
        """Give the frontend the ICE servers scrypted negotiates with.

        Scrypted only reveals its RTCConfiguration (including TURN servers and
        credentials) inside a signaling session, after the frontend has already
        built its peer connection — so serve servers captured from previous
        sessions. The first session falls back to HA's defaults.
        """
        config = WebRTCClientConfiguration()
        if self._cached_ice_servers:
            config.configuration.ice_servers = self._cached_ice_servers
        return config

    @callback
    def _store_ice_configuration(self, setup: dict) -> None:
        servers = [
            RTCIceServer(
                urls=server["urls"],
                username=server.get("username"),
                credential=server.get("credential"),
            )
            for server in (setup.get("configuration") or {}).get("iceServers") or []
            if server.get("urls")
        ]
        if servers:
            self._cached_ice_servers = servers

    async def async_handle_async_webrtc_offer(
        self, offer_sdp: str, session_id: str, send_message: WebRTCSendMessage
    ) -> None:
        """Start a scrypted signaling session for a HA frontend offer."""
        device = self.device
        if device is None:
            send_message(
                WebRTCError("scrypted_webrtc", "Scrypted device is unavailable")
            )
            return
        session = HomeAssistantSignalingSession(
            offer_sdp, send_message, on_setup=self._store_ice_configuration
        )
        self._webrtc_sessions[session_id] = session
        try:
            session.control = await device.startRTCSignalingSession(session)
        except Exception as err:  # noqa: BLE001 - surfaced to the frontend
            self._webrtc_sessions.pop(session_id, None)
            _LOGGER.exception("WebRTC negotiation failed for %s", self.entity_id)
            send_message(WebRTCError("scrypted_webrtc", str(err)))

    async def async_on_webrtc_candidate(
        self, session_id: str, candidate: RTCIceCandidateInit
    ) -> None:
        """Forward a HA frontend ICE candidate to the scrypted peer."""
        if session := self._webrtc_sessions.get(session_id):
            await session.add_client_candidate(candidate)

    @callback
    def close_webrtc_session(self, session_id: str) -> None:
        """Tear down the scrypted session when the frontend closes."""
        if session := self._webrtc_sessions.pop(session_id, None):
            self.hass.async_create_task(session.async_end())

    async def async_will_remove_from_hass(self) -> None:
        sessions = list(self._webrtc_sessions.values())
        self._webrtc_sessions.clear()
        for session in sessions:
            await session.async_end()
