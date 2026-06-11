"""Tests for scrypted cameras."""
from homeassistant.components.camera import async_get_image

from tests.test_binary_sensor import setup_entry


async def test_camera_created(hass, fake_sdk, enable_custom_integrations):
    await setup_entry(hass)
    state = hass.states.get("camera.front_door_cam")
    assert state is not None


async def test_camera_snapshot(hass, fake_sdk, enable_custom_integrations):
    await setup_entry(hass)
    image = await async_get_image(hass, "camera.front_door_cam")
    assert image.content == b"fake-jpeg"
    # Snapshot prefers takePicture when Camera interface present
    fake_sdk.systemManager.getDeviceById("cam1").takePicture.assert_awaited()


async def test_camera_stream_source_rewrites_localhost(
    hass, fake_sdk, enable_custom_integrations
):
    await setup_entry(hass)
    from homeassistant.components.camera import get_camera_from_entity_id

    camera = get_camera_from_entity_id(hass, "camera.front_door_cam")
    source = await camera.stream_source()
    # fake mediaManager returns rtsp://localhost:34567/stream; localhost must
    # be rewritten to the configured scrypted host
    assert source == "rtsp://1.2.3.4:34567/stream"


async def test_camera_edge_cases(hass, fake_sdk, enable_custom_integrations):
    await setup_entry(hass)
    from homeassistant.components.camera import get_camera_from_entity_id

    cam = get_camera_from_entity_id(hass, "camera.front_door_cam")
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

    # stream: non-rtsp url -> None
    fake_sdk.mediaManager.convertMediaObjectToJSON.return_value = {
        "url": "http://localhost/x"
    }
    assert await cam.stream_source() is None

    # stream: non-local host preserved as-is
    fake_sdk.mediaManager.convertMediaObjectToJSON.return_value = {
        "url": "rtsp://10.0.0.9:1/s"
    }
    assert await cam.stream_source() == "rtsp://10.0.0.9:1/s"

    # stream failure -> None
    fake_sdk.mediaManager.convertMediaObjectToJSON.side_effect = RuntimeError("x")
    assert await cam.stream_source() is None

    # device disappears -> everything degrades to None/False
    fake_sdk.systemManager.systemState.pop("cam1")
    assert cam.is_recording is False
    assert cam.motion_detection_enabled is False
    assert await cam.async_camera_image() is None
    assert await cam.stream_source() is None
