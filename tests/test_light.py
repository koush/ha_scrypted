"""Tests for scrypted lights."""
import copy

from tests.test_binary_sensor import setup_entry

TYPES = ["Camera", "Doorbell", "Light"]


async def test_light_discovered_with_modes_and_range(hass, fake_sdk, enable_custom_integrations):
    await setup_entry(hass, device_types=TYPES)
    state = hass.states.get("light.desk_light")
    assert state is not None
    assert state.state == "off"
    assert sorted(state.attributes["supported_color_modes"]) == ["color_temp", "hs"]
    assert state.attributes["max_color_temp_kelvin"] == 6500
    assert state.attributes["min_color_temp_kelvin"] == 2000


async def test_light_state_attributes_when_on(hass, fake_sdk, enable_custom_integrations):
    await setup_entry(hass, device_types=TYPES)
    fake_sdk.systemManager.set_property("light1", "on", True)
    await hass.async_block_till_done()
    state = hass.states.get("light.desk_light")
    assert state.state == "on"
    assert state.attributes["brightness"] == 128  # 50% -> 255 scale
    assert state.attributes["color_mode"] == "hs"  # hsv saturation 0.5 > 0
    assert state.attributes["hs_color"] == (120, 50.0)

    # desaturated -> reports color temp
    fake_sdk.systemManager.set_property("light1", "hsv", {"h": 0, "s": 0, "v": 1})
    await hass.async_block_till_done()
    state = hass.states.get("light.desk_light")
    assert state.attributes["color_mode"] == "color_temp"
    assert state.attributes["color_temp_kelvin"] == 3000

    # missing hsv -> hs_color is None and color_mode falls back to color_temp
    fake_sdk.systemManager.set_property("light1", "hsv", None)
    await hass.async_block_till_done()
    entity = hass.data["entity_components"]["light"].get_entity("light.desk_light")
    assert entity.hs_color is None
    state = hass.states.get("light.desk_light")
    assert state.attributes["color_mode"] == "color_temp"


async def test_light_commands(hass, fake_sdk, enable_custom_integrations):
    await setup_entry(hass, device_types=TYPES)
    device = fake_sdk.systemManager.getDeviceById("light1")

    await hass.services.async_call(
        "light", "turn_on",
        {"entity_id": "light.desk_light", "brightness": 255, "hs_color": [240, 100]},
        blocking=True,
    )
    device.turnOn.assert_awaited_once()
    device.setBrightness.assert_awaited_once_with(100)
    device.setHsv.assert_awaited_once_with(240, 1.0, 1)

    await hass.services.async_call(
        "light", "turn_on",
        {"entity_id": "light.desk_light", "color_temp_kelvin": 4000},
        blocking=True,
    )
    device.setColorTemperature.assert_awaited_once_with(4000)

    await hass.services.async_call(
        "light", "turn_off", {"entity_id": "light.desk_light"}, blocking=True
    )
    device.turnOff.assert_awaited_once()


async def test_onoff_only_light_and_kelvin_failure(
    hass, fake_sdk, system_state, enable_custom_integrations
):
    system_state["light2"] = copy.deepcopy(system_state["light1"])
    system_state["light2"]["name"] = {"value": "Plain Bulb"}
    system_state["light2"]["interfaces"] = {"value": ["OnOff", "Online"]}
    fake_sdk.systemManager.getDeviceById("light1").getTemperatureMaxK.side_effect = (
        RuntimeError("nope")
    )
    await setup_entry(hass, device_types=TYPES)

    plain = hass.states.get("light.plain_bulb")
    assert plain.attributes["supported_color_modes"] == ["onoff"]
    # kelvin fetch failure falls back to HA defaults without breaking setup
    desk = hass.states.get("light.desk_light")
    assert desk is not None


async def test_rgb_light_color_mode_and_command(
    hass, fake_sdk, system_state, enable_custom_integrations
):
    system_state["light3"] = copy.deepcopy(system_state["light1"])
    system_state["light3"]["name"] = {"value": "Rgb Strip"}
    system_state["light3"]["interfaces"] = {"value": ["OnOff", "ColorSettingRgb", "Online"]}
    del system_state["light3"]["hsv"]
    system_state["light3"]["rgb"] = {"value": {"r": 255, "g": 0, "b": 0}}
    system_state["light3"]["on"] = {"value": True}
    await setup_entry(hass, device_types=TYPES)

    state = hass.states.get("light.rgb_strip")
    assert state is not None
    assert state.attributes["supported_color_modes"] == ["rgb"]
    assert state.attributes["color_mode"] == "rgb"
    assert state.attributes["rgb_color"] == (255, 0, 0)

    device = fake_sdk.systemManager.getDeviceById("light3")
    await hass.services.async_call(
        "light", "turn_on",
        {"entity_id": "light.rgb_strip", "rgb_color": [10, 20, 30]},
        blocking=True,
    )
    device.setRgb.assert_awaited_once_with(10, 20, 30)

    # missing rgb -> rgb_color attribute is None
    fake_sdk.systemManager.set_property("light3", "rgb", None)
    await hass.async_block_till_done()
    state = hass.states.get("light.rgb_strip")
    assert state.attributes["rgb_color"] is None


async def test_rgb_and_temp_light_color_mode(
    hass, fake_sdk, system_state, enable_custom_integrations
):
    """A light with both ColorSettingRgb and ColorSettingTemperature (no Hsv)."""
    system_state["light4"] = copy.deepcopy(system_state["light1"])
    system_state["light4"]["name"] = {"value": "Rgb Temp Strip"}
    system_state["light4"]["interfaces"] = {
        "value": ["OnOff", "ColorSettingRgb", "ColorSettingTemperature", "Online"]
    }
    del system_state["light4"]["hsv"]
    system_state["light4"]["rgb"] = {"value": {"r": 255, "g": 0, "b": 0}}
    system_state["light4"]["colorTemperature"] = {"value": 3000}
    system_state["light4"]["on"] = {"value": True}
    await setup_entry(hass, device_types=TYPES)

    state = hass.states.get("light.rgb_temp_strip")
    assert state is not None
    assert sorted(state.attributes["supported_color_modes"]) == ["color_temp", "rgb"]
    assert state.attributes["color_mode"] == "rgb"

    fake_sdk.systemManager.set_property(
        "light4", "rgb", {"r": 200, "g": 200, "b": 200}
    )
    await hass.async_block_till_done()
    state = hass.states.get("light.rgb_temp_strip")
    assert state.attributes["color_mode"] == "color_temp"
