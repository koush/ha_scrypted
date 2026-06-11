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
