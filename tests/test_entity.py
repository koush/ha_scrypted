"""Tests for discovery helpers."""
from types import SimpleNamespace

from custom_components.scrypted.entity import device_matches


def make_client(fake_sdk, device_types=None):
    options = {}
    if device_types is not None:
        options["device_types"] = device_types
    return SimpleNamespace(sdk=fake_sdk, entry=SimpleNamespace(options=options))


def test_device_matches_interface(fake_sdk):
    client = make_client(fake_sdk)
    assert device_matches(client, "cam1", "MotionSensor")
    assert not device_matches(client, "cam1", "FloodSensor")


def test_device_matches_missing_device(fake_sdk):
    assert not device_matches(make_client(fake_sdk), "nope", "MotionSensor")


def test_default_allowlist_is_cameras_and_doorbells(fake_sdk):
    client = make_client(fake_sdk)
    # leak1 is type Sensor: excluded by default, included when selected
    assert not device_matches(client, "leak1", "FloodSensor")
    assert device_matches(
        make_client(fake_sdk, ["Camera", "Doorbell", "Sensor"]), "leak1", "FloodSensor"
    )
    # plugin1 is type API (plumbing, never offered in the selector)
    assert not device_matches(client, "plugin1", "Online")


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


async def test_ha_imported_devices_are_excluded(hass, fake_sdk, enable_custom_integrations):
    """Devices provided by @scrypted/homeassistant never round-trip into HA."""
    from tests.test_binary_sensor import setup_entry

    await setup_entry(hass)
    # haimport1 has VideoCamera + allowlisted type, but must produce nothing
    assert not [
        s for s in hass.states.async_all() if "imported_ha_light" in s.entity_id
    ]
