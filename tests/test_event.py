"""Tests for scrypted event entities."""
from homeassistant.helpers.dispatcher import async_dispatcher_send

from custom_components.scrypted.const import SIGNAL_CONNECTION
from tests.test_binary_sensor import setup_entry


async def test_object_detection_event(hass, fake_sdk, enable_custom_integrations):
    await setup_entry(hass)

    state = hass.states.get("event.porch_front_door_cam_object_detected")
    assert state is not None
    assert "person" in state.attributes["event_types"]

    fake_sdk.systemManager.fire_device_event(
        "cam1",
        "ObjectDetector",
        {
            "detections": [
                {"className": "person", "score": 0.92, "zones": ["porch"]},
            ],
            "timestamp": 1,
        },
    )
    await hass.async_block_till_done()

    state = hass.states.get("event.porch_front_door_cam_object_detected")
    assert state.attributes["event_type"] == "person"
    assert state.attributes["score"] == 0.92


async def test_unknown_detection_class_extends_event_types(
    hass, fake_sdk, enable_custom_integrations
):
    await setup_entry(hass)
    fake_sdk.systemManager.fire_device_event(
        "cam1",
        "ObjectDetector",
        {"detections": [{"className": "raccoon", "score": 0.5}], "timestamp": 1},
    )
    await hass.async_block_till_done()
    state = hass.states.get("event.porch_front_door_cam_object_detected")
    assert state.attributes["event_type"] == "raccoon"


async def test_doorbell_press_event(hass, fake_sdk, enable_custom_integrations):
    await setup_entry(hass)

    state = hass.states.get("event.doorbell_doorbell")
    assert state is not None

    fake_sdk.systemManager.set_property("bell1", "binaryState", True)
    await hass.async_block_till_done()
    state = hass.states.get("event.doorbell_doorbell")
    assert state.attributes["event_type"] == "ring"

    # Releasing must not fire another event
    last_changed = state.last_changed
    fake_sdk.systemManager.set_property("bell1", "binaryState", False)
    await hass.async_block_till_done()
    assert hass.states.get("event.doorbell_doorbell").last_changed == last_changed


async def test_object_types_failure_skips_entity(
    hass, fake_sdk, enable_custom_integrations
):
    """Unknown classes -> no entity; motion is filtered so it could never fire."""
    fake_sdk.systemManager.getDeviceById("cam1").getObjectTypes.side_effect = (
        RuntimeError("nope")
    )
    await setup_entry(hass)
    assert hass.states.get("event.porch_front_door_cam_object_detected") is None


async def test_motion_only_detector_skips_entity(
    hass, fake_sdk, enable_custom_integrations
):
    """Motion-only detectors are covered by the motion binary_sensor."""
    fake_sdk.systemManager.getDeviceById("cam1").getObjectTypes.return_value = {
        "classes": ["motion"]
    }
    await setup_entry(hass)
    assert hass.states.get("event.porch_front_door_cam_object_detected") is None


async def test_motion_class_excluded_from_event_types(
    hass, fake_sdk, enable_custom_integrations
):
    fake_sdk.systemManager.getDeviceById("cam1").getObjectTypes.return_value = {
        "classes": ["motion", "person", "car"]
    }
    await setup_entry(hass)
    state = hass.states.get("event.porch_front_door_cam_object_detected")
    assert state.attributes["event_types"] == ["person", "car"]


async def test_motion_detections_do_not_fire_events(
    hass, fake_sdk, enable_custom_integrations
):
    await setup_entry(hass)

    # scrypted's motion pipeline reports motion as a detection class; the
    # motion binary_sensor owns that signal, so the event entity ignores it.
    fake_sdk.systemManager.fire_device_event(
        "cam1",
        "ObjectDetector",
        {"detections": [{"className": "motion", "score": 1}], "timestamp": 1},
    )
    await hass.async_block_till_done()
    state = hass.states.get("event.porch_front_door_cam_object_detected")
    assert state.state == "unknown"
    assert "motion" not in state.attributes["event_types"]

    # mixed payloads only fire the classified objects
    fake_sdk.systemManager.fire_device_event(
        "cam1",
        "ObjectDetector",
        {
            "detections": [
                {"className": "motion", "score": 1},
                {"className": "person", "score": 0.9},
            ],
            "timestamp": 2,
        },
    )
    await hass.async_block_till_done()
    state = hass.states.get("event.porch_front_door_cam_object_detected")
    assert state.attributes["event_type"] == "person"
    assert "motion" not in state.attributes["event_types"]


async def test_detection_without_class_ignored(
    hass, fake_sdk, enable_custom_integrations
):
    await setup_entry(hass)
    fake_sdk.systemManager.fire_device_event(
        "cam1", "ObjectDetector", {"detections": [{"score": 1.0}], "timestamp": 1}
    )
    await hass.async_block_till_done()
    state = hass.states.get("event.porch_front_door_cam_object_detected")
    assert state.state == "unknown"


async def test_connection_signal_handling(hass, fake_sdk, enable_custom_integrations):
    entry = await setup_entry(hass)
    client = entry.runtime_data.client
    signal = SIGNAL_CONNECTION.format(entry.entry_id)

    # connection lost: no re-register, state written
    async_dispatcher_send(hass, signal, False)
    await hass.async_block_till_done()

    # reconnected: object detection listener re-registers
    async_dispatcher_send(hass, signal, True)
    await hass.async_block_till_done()
    assert ("cam1", "ObjectDetector") in fake_sdk.systemManager.device_listeners

    # reconnected while sdk unset: register is a guarded no-op
    client.sdk = None
    async_dispatcher_send(hass, signal, True)
    await hass.async_block_till_done()
    client.sdk = fake_sdk
