"""Tests for discovery helpers."""
from custom_components.scrypted.entity import device_matches


def test_device_matches_interface(fake_sdk):
    assert device_matches(fake_sdk, "cam1", "MotionSensor")
    assert not device_matches(fake_sdk, "leak1", "MotionSensor")


def test_device_matches_missing_device(fake_sdk):
    assert not device_matches(fake_sdk, "nope", "MotionSensor")


def test_excluded_types_never_match(fake_sdk):
    # plugin1 has Online but is type API (excluded plumbing)
    assert not device_matches(fake_sdk, "plugin1", "Online")


def test_entity_handles_missing_device_and_values(fake_sdk):
    """Entities degrade gracefully when state or devices disappear."""
    from types import SimpleNamespace

    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.scrypted.binary_sensor import (
        BINARY_SENSORS,
        ScryptedBinarySensor,
    )
    from custom_components.scrypted.const import DOMAIN

    client = SimpleNamespace(sdk=fake_sdk, connected=True)
    entry = MockConfigEntry(domain=DOMAIN)
    description = next(d for d in BINARY_SENSORS if d.key == "motion")
    entity = ScryptedBinarySensor(client, entry, "cam1", description)

    # missing property value -> unknown
    fake_sdk.systemManager.systemState["cam1"].pop("motionDetected")
    assert entity.is_on is None

    # device disappears -> no value, unavailable
    fake_sdk.systemManager.systemState.pop("cam1")
    assert entity.raw_value is None
    assert entity.available is False

    # client disconnected -> unavailable
    client.connected = False
    assert entity.available is False

    # no sdk -> no device
    client.sdk = None
    assert entity.device is None
