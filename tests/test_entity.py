"""Tests for discovery helpers."""
from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity import EntityDescription
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.scrypted.const import DOMAIN, SIGNAL_NEW_DEVICE
from custom_components.scrypted.entity import (
    ScryptedDeviceEntity,
    ScryptedEntityDescriptionMixin,
    async_setup_scrypted_platform,
    device_matches,
)
from tests.conftest import setup_entry


@dataclass(frozen=True, kw_only=True)
class MotionDescription(ScryptedEntityDescriptionMixin, EntityDescription):
    """Minimal description for exercising the base entity."""


MOTION_DESCRIPTION = MotionDescription(
    key="motion", interface="MotionSensor", state_property="motionDetected"
)


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
    client = SimpleNamespace(sdk=fake_sdk, connected=True)
    entry = MockConfigEntry(domain=DOMAIN)
    entity = ScryptedDeviceEntity(client, entry, "cam1", MOTION_DESCRIPTION)

    # missing property value -> unknown
    fake_sdk.systemManager.systemState["cam1"].pop("motionDetected")
    assert entity.raw_value is None

    # device reports offline via the Online interface -> unavailable
    fake_sdk.systemManager.set_property("cam1", "online", False)
    assert entity.available is False
    fake_sdk.systemManager.set_property("cam1", "online", True)
    assert entity.available is True

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
    await setup_entry(hass)
    # haimport1 has VideoCamera + allowlisted type, but must produce nothing
    assert not [
        s for s in hass.states.async_all() if "imported_ha_light" in s.entity_id
    ]


async def test_setup_scrypted_platform_dedups_and_discovers_new(
    hass, fake_sdk, enable_custom_integrations
):
    entry = await setup_entry(hass)
    added: list = []
    calls: list[str] = []

    class FakeEntity:
        def __init__(self, uid):
            self._attr_unique_id = uid

        @property
        def unique_id(self):
            return self._attr_unique_id

    async def discover(device_id):  # async discover_fn is supported
        calls.append(device_id)
        return [FakeEntity("same-uid")]

    await async_setup_scrypted_platform(hass, entry, added.extend, discover)
    assert calls  # swept existing devices
    assert len(added) == 1  # duplicates suppressed across devices

    async_dispatcher_send(hass, SIGNAL_NEW_DEVICE.format(entry.entry_id), "cam1")
    await hass.async_block_till_done()
    assert len(added) == 1  # same uid still suppressed


async def test_setup_scrypted_platform_no_client(hass, enable_custom_integrations):
    entry = SimpleNamespace(runtime_data=SimpleNamespace(client=None))
    await async_setup_scrypted_platform(hass, entry, lambda _: None, lambda d: [])
    # no exception is the assertion


async def test_device_command_wraps_errors(hass, fake_sdk, enable_custom_integrations):
    entry = await setup_entry(hass)
    client = entry.runtime_data.client
    entity = ScryptedDeviceEntity(client, entry, "cam1", MOTION_DESCRIPTION)
    entity.entity_id = "camera.test"
    fake_sdk.systemManager.getDeviceById("cam1").takePicture.side_effect = RuntimeError("boom")
    with pytest.raises(HomeAssistantError, match="takePicture"):
        await entity._async_device_command("takePicture")

    client.sdk = None  # device gone -> HomeAssistantError, not AttributeError
    with pytest.raises(HomeAssistantError, match="unavailable"):
        await entity._async_device_command("takePicture")
    client.sdk = fake_sdk

    # a HomeAssistantError raised by the device method itself propagates
    # unwrapped, rather than being re-wrapped with a duplicated message.
    fake_sdk.systemManager.getDeviceById("cam1").takePicture.side_effect = (
        HomeAssistantError("already user-friendly")
    )
    with pytest.raises(HomeAssistantError, match="already user-friendly"):
        await entity._async_device_command("takePicture")
