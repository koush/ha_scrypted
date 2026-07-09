"""Tests for scrypted covers."""
import copy

from tests.test_binary_sensor import setup_entry

TYPES = ["Camera", "Doorbell", "Garage", "Entry", "WindowCovering"]


async def test_garage_discovered_with_state(hass, fake_sdk, enable_custom_integrations):
    await setup_entry(hass, device_types=TYPES)
    state = hass.states.get("cover.garage_door")
    assert state is not None
    assert state.state == "closed"
    assert state.attributes["device_class"] == "garage"

    fake_sdk.systemManager.set_property("garage1", "entryOpen", True)
    await hass.async_block_till_done()
    assert hass.states.get("cover.garage_door").state == "open"

    # jammed reads as unknown, not open/closed
    fake_sdk.systemManager.set_property("garage1", "entryOpen", "jammed")
    await hass.async_block_till_done()
    assert hass.states.get("cover.garage_door").state == "unknown"


async def test_cover_commands(hass, fake_sdk, enable_custom_integrations):
    await setup_entry(hass, device_types=TYPES)
    device = fake_sdk.systemManager.getDeviceById("garage1")

    await hass.services.async_call(
        "cover", "open_cover", {"entity_id": "cover.garage_door"}, blocking=True
    )
    device.openEntry.assert_awaited_once()

    await hass.services.async_call(
        "cover", "close_cover", {"entity_id": "cover.garage_door"}, blocking=True
    )
    device.closeEntry.assert_awaited_once()


async def test_stateless_cover_assumed(hass, fake_sdk, system_state, enable_custom_integrations):
    # a gate with Entry but no EntrySensor
    system_state["gate1"] = copy.deepcopy(system_state["garage1"])
    system_state["gate1"]["name"] = {"value": "Front Gate"}
    system_state["gate1"]["type"] = {"value": "Entry"}
    system_state["gate1"]["interfaces"] = {"value": ["Entry", "Online"]}
    await setup_entry(hass, device_types=TYPES)
    state = hass.states.get("cover.front_gate")
    assert state is not None
    assert state.state == "unknown"
    assert state.attributes.get("assumed_state") is True
