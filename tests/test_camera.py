"""Tests for scrypted cameras (snapshot-only by design)."""

from homeassistant.components.camera import (
    CAMERA_IMAGE_TIMEOUT,
    DOMAIN as CAMERA_DOMAIN,
    SERVICE_SNAPSHOT,
    CameraEntityFeature,
    async_get_image,
    get_camera_from_entity_id,
)
from homeassistant.helpers.dispatcher import async_dispatcher_send

from custom_components.scrypted.camera import FRESH_PICTURE_TIMEOUT_MS
from custom_components.scrypted.const import SIGNAL_CONNECTION
from tests.conftest import setup_entry


async def test_camera_created(hass, fake_sdk, enable_custom_integrations):
    """Camera created."""
    await setup_entry(hass)
    state = hass.states.get("camera.porch_front_door_cam")
    assert state is not None
    assert state.attributes["device_id"] == "cam1"


async def test_camera_snapshot(hass, fake_sdk, enable_custom_integrations):
    """Camera snapshot."""
    await setup_entry(hass)
    image = await async_get_image(hass, "camera.porch_front_door_cam")
    assert image.content == b"fake-jpeg"
    # Snapshot prefers takePicture when Camera interface present
    fake_sdk.systemManager.getDeviceById("cam1").takePicture.assert_awaited()


async def test_camera_has_no_stream_support(hass, fake_sdk, enable_custom_integrations):
    """Live streaming is intentionally unsupported; NVR cards handle live view."""
    await setup_entry(hass)
    cam = get_camera_from_entity_id(hass, "camera.porch_front_door_cam")
    assert not cam.supported_features & CameraEntityFeature.STREAM
    assert await cam.stream_source() is None
    assert cam._supports_native_async_webrtc is False


async def test_camera_edge_cases(hass, fake_sdk, enable_custom_integrations):
    """Camera edge cases."""
    await setup_entry(hass)
    cam = get_camera_from_entity_id(hass, "camera.porch_front_door_cam")
    bell = get_camera_from_entity_id(hass, "camera.doorbell")

    assert cam.is_recording is True
    assert bell.is_recording is False
    assert cam.motion_detection_enabled is True

    # snapshot falls back to getVideoStream without the Camera interface
    image = await bell.async_camera_image()
    assert image == b"fake-jpeg"
    fake_sdk.systemManager.getDeviceById("bell1").getVideoStream.assert_awaited()

    # snapshot failure -> None
    fake_sdk.mediaManager.convertMediaObjectToBuffer.side_effect = RuntimeError("x")
    assert await cam.async_camera_image() is None

    # device disappears -> everything degrades to None/False
    fake_sdk.systemManager.systemState.pop("cam1")
    assert cam.is_recording is False
    assert cam.motion_detection_enabled is False
    assert await cam.async_camera_image() is None


async def test_camera_updates_on_events(hass, fake_sdk, enable_custom_integrations):
    """Dispatcher signals push state writes through the base entity."""
    entry = await setup_entry(hass)
    assert hass.states.get("camera.porch_front_door_cam").state == "recording"

    # property update -> device-update signal -> new state written
    fake_sdk.systemManager.set_property("cam1", "recordingActive", False)
    await hass.async_block_till_done()
    assert hass.states.get("camera.porch_front_door_cam").state == "idle"

    # connection loss -> connection signal -> entity goes unavailable
    entry.runtime_data.client.connected = False
    async_dispatcher_send(hass, SIGNAL_CONNECTION.format(entry.entry_id), False)
    await hass.async_block_till_done()
    assert hass.states.get("camera.porch_front_door_cam").state == "unavailable"


async def test_snapshot_service_requests_a_fresh_frame(
    hass, fake_sdk, enable_custom_integrations, tmp_path
):
    """camera.snapshot asks scrypted for an event capture, never a cached one."""
    await setup_entry(hass)
    hass.config.allowlist_external_dirs = {str(tmp_path)}
    target = tmp_path / "snap.jpg"

    await hass.services.async_call(
        CAMERA_DOMAIN,
        SERVICE_SNAPSHOT,
        {"entity_id": "camera.porch_front_door_cam", "filename": str(target)},
        blocking=True,
    )

    assert target.read_bytes() == b"fake-jpeg"
    fake_sdk.systemManager.getDeviceById("cam1").takePicture.assert_awaited_once_with(
        {"reason": "event", "timeout": FRESH_PICTURE_TIMEOUT_MS}
    )


async def test_thumbnail_keeps_cache_friendly_request(
    hass, fake_sdk, enable_custom_integrations
):
    """A request with dimensions is a thumbnail refresh, where a recent image is fine."""
    await setup_entry(hass)

    image = await async_get_image(
        hass, "camera.porch_front_door_cam", width=320, height=180
    )

    assert image.content == b"fake-jpeg"
    fake_sdk.systemManager.getDeviceById("cam1").takePicture.assert_awaited_once_with()


def test_fresh_picture_timeout_finishes_before_home_assistant_gives_up():
    """Scrypted's wait must end inside Home Assistant's own image timeout."""
    assert 0 < FRESH_PICTURE_TIMEOUT_MS < CAMERA_IMAGE_TIMEOUT * 1000
