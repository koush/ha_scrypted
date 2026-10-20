"""Tests for scrypted buttons."""

from dataclasses import replace
from unittest.mock import patch

import pytest

from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from custom_components.scrypted.button import BUTTONS
from tests.conftest import setup_entry

RESTART = "button.porch_front_door_cam_restart"


async def _setup_with_restart_enabled(hass):
    buttons = tuple(
        replace(description, entity_registry_enabled_default=True)
        for description in BUTTONS
    )
    with patch("custom_components.scrypted.button.BUTTONS", buttons):
        return await setup_entry(hass)


async def test_restart_button_created_disabled(
    hass, fake_sdk, enable_custom_integrations
):
    """Devices with Reboot get a disabled Restart button; others get none."""
    await setup_entry(hass)
    registry = er.async_get(hass)

    entity = registry.async_get(RESTART)
    assert entity is not None
    assert entity.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert entity.entity_category is EntityCategory.CONFIG
    assert hass.states.get(RESTART) is None
    # bell1 has no Reboot interface
    assert registry.async_get("button.doorbell_restart") is None


async def test_restart_button_reboots_device(
    hass, fake_sdk, enable_custom_integrations
):
    """Pressing Restart calls reboot on the device."""
    await _setup_with_restart_enabled(hass)
    device = fake_sdk.systemManager.getDeviceById("cam1")

    await hass.services.async_call(
        "button", "press", {"entity_id": RESTART}, blocking=True
    )
    device.reboot.assert_awaited_once_with()


async def test_restart_button_surfaces_failure(
    hass, fake_sdk, enable_custom_integrations
):
    """A failed reboot is reported as a service error."""
    await _setup_with_restart_enabled(hass)
    fake_sdk.systemManager.getDeviceById("cam1").reboot.side_effect = RuntimeError(
        "camera unreachable"
    )

    with pytest.raises(HomeAssistantError, match="camera unreachable"):
        await hass.services.async_call(
            "button", "press", {"entity_id": RESTART}, blocking=True
        )
