"""Tests for scrypted switches."""
from tests.test_binary_sensor import setup_entry

TYPES = ["Camera", "Doorbell", "Switch", "Outlet"]


async def test_outlet_discovered_with_device_class(hass, fake_sdk, enable_custom_integrations):
    await setup_entry(hass, device_types=TYPES)
    state = hass.states.get("switch.heater_plug")
    assert state is not None
    assert state.state == "on"
    assert state.attributes["device_class"] == "outlet"


async def test_switch_not_discovered_without_allowlist(hass, fake_sdk, enable_custom_integrations):
    await setup_entry(hass)  # default allowlist: no Switch/Outlet
    assert hass.states.get("switch.heater_plug") is None


async def test_switch_commands_and_push_update(hass, fake_sdk, enable_custom_integrations):
    await setup_entry(hass, device_types=TYPES)
    device = fake_sdk.systemManager.getDeviceById("outlet1")

    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.heater_plug"}, blocking=True
    )
    device.turnOff.assert_awaited_once()
    # state is push-confirmed, not optimistic
    assert hass.states.get("switch.heater_plug").state == "on"
    fake_sdk.systemManager.set_property("outlet1", "on", False)
    await hass.async_block_till_done()
    assert hass.states.get("switch.heater_plug").state == "off"

    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.heater_plug"}, blocking=True
    )
    device.turnOn.assert_awaited_once()
