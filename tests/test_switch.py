"""Tests for scrypted switches."""

from homeassistant.const import EntityCategory
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send

from custom_components.scrypted.config_flow import DEVICE_TYPE_OPTIONS
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


NOTIFIER_ENTITY = "switch.scrypted_iphone_app_alex_notifications"


def add_app_notifier(fake_sdk):
    """Add a Scrypted NVR app notifier, which scrypted can turn on and off."""
    fake_sdk.systemManager.systemState["notifier1"] = state(
        name="Scrypted iPhone App (alex)",
        type="Notifier",
        info={},
        pluginId="@scrypted/nvr",
        interfaces=["@scrypted/nvr:Notifier", "Notifier", "OnOff", "Settings"],
        on=True,
    )


def test_notifier_is_offered_as_a_device_type():
    """Notifier is a selectable device type in the options form."""
    assert "Notifier" in DEVICE_TYPE_OPTIONS


async def test_notifier_not_exposed_by_default(
    hass, fake_sdk, enable_custom_integrations
):
    """Notification switches are opt-in: they can mute other people's phones."""
    add_app_notifier(fake_sdk)
    await setup_entry(hass)
    assert hass.states.get(NOTIFIER_ENTITY) is None


async def test_app_notifier_gets_notifications_switch(
    hass, fake_sdk, enable_custom_integrations
):
    """Selecting Notifier gives each app notifier a config switch that mutes it."""
    add_app_notifier(fake_sdk)
    await setup_entry(hass, device_types=[*TYPES, "Notifier"])

    state_obj = hass.states.get(NOTIFIER_ENTITY)
    assert state_obj is not None
    assert state_obj.state == "on"
    assert state_obj.attributes["icon"] == "mdi:bell"
    entity = er.async_get(hass).async_get(NOTIFIER_ENTITY)
    assert entity.entity_category is EntityCategory.CONFIG

    device = fake_sdk.systemManager.getDeviceById("notifier1")
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": NOTIFIER_ENTITY}, blocking=True
    )
    device.turnOff.assert_awaited_once()
    fake_sdk.systemManager.set_property("notifier1", "on", False)
    await hass.async_block_till_done()
    assert hass.states.get(NOTIFIER_ENTITY).state == "off"


async def test_notifier_without_onoff_gets_no_switch(
    hass, fake_sdk, enable_custom_integrations
):
    """Notifiers scrypted cannot turn on and off produce no entity."""
    fake_sdk.systemManager.systemState["pushover1"] = state(
        name="Pushover",
        type="Notifier",
        info={},
        interfaces=["Notifier", "Settings"],
    )
    await setup_entry(hass, device_types=[*TYPES, "Notifier"])
    assert not [s for s in hass.states.async_all() if "pushover" in s.entity_id]
