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


def _make_fake_rtc_camera(fake_sdk):
    """Script the camera side of the signaling dance like @scrypted/webrtc."""
    from unittest.mock import AsyncMock

    fake_sdk.systemManager.systemState["cam1"]["interfaces"]["value"].append(
        "RTCSignalingChannel"
    )
    device = fake_sdk.systemManager.getDeviceById("cam1")
    camera_side = {
        "received_client_candidates": [],
        "control": AsyncMock(),
        "session": None,
    }

    async def start_rtc_signaling_session(session):
        camera_side["session"] = session
        await session.getOptions()

        async def send_ice_candidate(candidate):
            camera_side["received_client_candidates"].append(candidate)

        offer = await session.createLocalDescription("offer", {}, send_ice_candidate)
        assert offer == {"type": "offer", "sdp": "ha-offer-sdp"}
        await session.setRemoteDescription(
            {"type": "answer", "sdp": "scrypted-answer-sdp"}, {}
        )
        await session.addIceCandidate(
            {"candidate": "candidate:1", "sdpMid": "0", "sdpMLineIndex": 0}
        )
        return camera_side["control"]

    object.__setattr__(
        device,
        "startRTCSignalingSession",
        AsyncMock(side_effect=start_rtc_signaling_session),
    )
    return camera_side


async def test_webrtc_offer_answer_and_candidates(
    hass, fake_sdk, enable_custom_integrations
):
    from homeassistant.components.camera import (
        WebRTCAnswer,
        WebRTCCandidate,
        get_camera_from_entity_id,
    )
    from webrtc_models import RTCIceCandidateInit

    camera_side = _make_fake_rtc_camera(fake_sdk)
    await setup_entry(hass)
    cam = get_camera_from_entity_id(hass, "camera.front_door_cam")
    assert cam._supports_native_async_webrtc is True

    messages = []
    await cam.async_handle_async_webrtc_offer("ha-offer-sdp", "sess1", messages.append)
    await hass.async_block_till_done()

    answers = [m for m in messages if isinstance(m, WebRTCAnswer)]
    assert answers and answers[0].answer == "scrypted-answer-sdp"
    candidates = [m for m in messages if isinstance(m, WebRTCCandidate)]
    assert candidates and candidates[0].candidate.candidate == "candidate:1"

    # HA -> camera trickle
    await cam.async_on_webrtc_candidate(
        "sess1", RTCIceCandidateInit("candidate:ha", sdp_mid="0", sdp_m_line_index=0)
    )
    assert camera_side["received_client_candidates"] == [
        {"candidate": "candidate:ha", "sdpMid": "0", "sdpMLineIndex": 0}
    ]
    # unknown session id is ignored
    await cam.async_on_webrtc_candidate(
        "ghost", RTCIceCandidateInit("candidate:x", sdp_mid="0", sdp_m_line_index=0)
    )

    cam.close_webrtc_session("sess1")
    await hass.async_block_till_done()
    camera_side["control"].endSession.assert_awaited()
    # double-close is a no-op
    cam.close_webrtc_session("sess1")


async def test_webrtc_candidates_buffered_before_negotiation(
    hass, fake_sdk, enable_custom_integrations
):
    """HA candidates arriving before the camera asks for the offer are queued."""
    import asyncio
    from unittest.mock import AsyncMock

    from homeassistant.components.camera import get_camera_from_entity_id
    from webrtc_models import RTCIceCandidateInit

    fake_sdk.systemManager.systemState["cam1"]["interfaces"]["value"].append(
        "RTCSignalingChannel"
    )
    device = fake_sdk.systemManager.getDeviceById("cam1")
    proceed = asyncio.Event()
    received = []

    async def slow_start(session):
        await proceed.wait()

        async def send_ice_candidate(candidate):
            received.append(candidate)

        await session.createLocalDescription("offer", {}, send_ice_candidate)
        return AsyncMock()

    object.__setattr__(
        device, "startRTCSignalingSession", AsyncMock(side_effect=slow_start)
    )
    await setup_entry(hass)
    cam = get_camera_from_entity_id(hass, "camera.front_door_cam")

    task = hass.async_create_task(
        cam.async_handle_async_webrtc_offer("ha-offer-sdp", "sess1", lambda m: None)
    )
    await asyncio.sleep(0)
    await cam.async_on_webrtc_candidate(
        "sess1", RTCIceCandidateInit("candidate:early", sdp_mid="0", sdp_m_line_index=0)
    )
    assert received == []
    proceed.set()
    await task
    assert received == [
        {"candidate": "candidate:early", "sdpMid": "0", "sdpMLineIndex": 0}
    ]


async def test_webrtc_failure_sends_error(hass, fake_sdk, enable_custom_integrations):
    from unittest.mock import AsyncMock

    from homeassistant.components.camera import (
        WebRTCError,
        get_camera_from_entity_id,
    )

    fake_sdk.systemManager.systemState["cam1"]["interfaces"]["value"].append(
        "RTCSignalingChannel"
    )
    device = fake_sdk.systemManager.getDeviceById("cam1")
    object.__setattr__(
        device,
        "startRTCSignalingSession",
        AsyncMock(side_effect=RuntimeError("kaboom")),
    )
    await setup_entry(hass)
    cam = get_camera_from_entity_id(hass, "camera.front_door_cam")

    messages = []
    await cam.async_handle_async_webrtc_offer("ha-offer-sdp", "sess1", messages.append)
    assert any(isinstance(m, WebRTCError) for m in messages)

    # device gone -> error message too
    fake_sdk.systemManager.systemState.pop("cam1")
    messages.clear()
    await cam.async_handle_async_webrtc_offer("ha-offer-sdp", "sess2", messages.append)
    assert any(isinstance(m, WebRTCError) for m in messages)


async def test_webrtc_sessions_closed_on_entity_removal(
    hass, fake_sdk, enable_custom_integrations
):
    from homeassistant.components.camera import get_camera_from_entity_id

    camera_side = _make_fake_rtc_camera(fake_sdk)
    entry = await setup_entry(hass)
    cam = get_camera_from_entity_id(hass, "camera.front_door_cam")
    await cam.async_handle_async_webrtc_offer("ha-offer-sdp", "sess1", lambda m: None)
    await hass.async_block_till_done()

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    camera_side["control"].endSession.assert_awaited()


async def test_non_rtc_camera_keeps_rtsp_only(
    hass, fake_sdk, enable_custom_integrations
):
    """Cameras without RTCSignalingChannel stay on the RTSP code path."""
    from homeassistant.components.camera import get_camera_from_entity_id

    await setup_entry(hass)
    bell = get_camera_from_entity_id(hass, "camera.doorbell")
    assert bell._supports_native_async_webrtc is False


async def test_signaling_session_guards():
    """Direct guards: refuse to answer, swallow endSession failures."""
    from unittest.mock import AsyncMock

    import pytest

    from custom_components.scrypted.webrtc import HomeAssistantSignalingSession

    session = HomeAssistantSignalingSession("sdp", lambda m: None)
    with pytest.raises(ValueError):
        await session.createLocalDescription("answer", {})

    control = AsyncMock()
    control.endSession.side_effect = RuntimeError("x")
    session.control = control
    await session.async_end()
    assert session.control is None
