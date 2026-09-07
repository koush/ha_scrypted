"""Tests for scrypted switches."""

from homeassistant.helpers.dispatcher import async_dispatcher_send

from custom_components.scrypted.const import SIGNAL_NEW_DEVICE
from tests.conftest import setup_entry, state

TYPES = ["Camera", "Doorbell", "Switch", "Outlet"]


async def test_outlet_discovered_with_device_class(
    hass, fake_sdk, enable_custom_integrations
):
    """Outlet discovered with device class."""
    await setup_entry(hass, device_types=TYPES)
    state_obj = hass.states.get("switch.heater_plug")
    assert state_obj is not None
    assert state_obj.state == "on"
    assert state_obj.attributes["device_class"] == "outlet"


async def test_switch_not_discovered_without_allowlist(
    hass, fake_sdk, enable_custom_integrations
):
    """Switch not discovered without allowlist."""
    await setup_entry(hass)  # default allowlist: no Switch/Outlet
    assert hass.states.get("switch.heater_plug") is None


async def test_switch_commands_and_push_update(
    hass, fake_sdk, enable_custom_integrations
):
    """Switch commands and push update."""
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


async def test_plain_switch_gets_switch_device_class(
    hass, fake_sdk, enable_custom_integrations
):
    """Plain switch gets switch device class."""
    fake_sdk.systemManager.systemState["switch1"] = state(
        name="Porch Light Relay",
        type="Switch",
        info={},
        interfaces=["OnOff", "Online"],
        on=False,
        online=True,
    )
    await setup_entry(hass, device_types=TYPES)
    state_obj = hass.states.get("switch.porch_light_relay")
    assert state_obj is not None
    assert state_obj.state == "off"
    assert state_obj.attributes["device_class"] == "switch"


async def test_new_device_signal_ignored_for_unknown_or_disconnected(
    hass, fake_sdk, enable_custom_integrations
):
    """New device signal ignored for unknown or disconnected."""
    entry = await setup_entry(hass, device_types=TYPES)
    before = len(hass.states.async_entity_ids("switch"))

    # unknown device id: getDeviceById returns None
    async_dispatcher_send(hass, SIGNAL_NEW_DEVICE.format(entry.entry_id), "nope")
    await hass.async_block_till_done()
    assert len(hass.states.async_entity_ids("switch")) == before

    # SDK dropped (disconnected) while a new-device signal arrives
    entry.runtime_data.client.sdk = None
    async_dispatcher_send(hass, SIGNAL_NEW_DEVICE.format(entry.entry_id), "outlet1")
    await hass.async_block_till_done()
    assert len(hass.states.async_entity_ids("switch")) == before
