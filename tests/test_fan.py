"""Tests for scrypted fans."""
from tests.test_binary_sensor import setup_entry

TYPES = ["Camera", "Doorbell", "Fan"]


async def test_fan_discovered_with_speed_and_presets(hass, fake_sdk, enable_custom_integrations):
    await setup_entry(hass, device_types=TYPES)
    state = hass.states.get("fan.attic_fan")
    assert state is not None
    assert state.state == "on"  # speed 2 of 4
    assert state.attributes["percentage"] == 50
    assert state.attributes["preset_modes"] == ["Manual", "Auto"]
    assert state.attributes["preset_mode"] == "Manual"


async def test_fan_commands(hass, fake_sdk, enable_custom_integrations):
    await setup_entry(hass, device_types=TYPES)
    device = fake_sdk.systemManager.getDeviceById("fan1")

    await hass.services.async_call(
        "fan", "set_percentage",
        {"entity_id": "fan.attic_fan", "percentage": 75},
        blocking=True,
    )
    device.setFan.assert_awaited_with({"speed": 3})

    await hass.services.async_call(
        "fan", "turn_off", {"entity_id": "fan.attic_fan"}, blocking=True
    )
    device.setFan.assert_awaited_with({"speed": 0})

    # turn_on restores the last observed non-zero speed
    fake_sdk.systemManager.set_property(
        "fan1", "fan", {"speed": 0, "maxSpeed": 4, "mode": "Manual", "availableModes": ["Manual", "Auto"]}
    )
    await hass.async_block_till_done()
    await hass.services.async_call(
        "fan", "turn_on", {"entity_id": "fan.attic_fan"}, blocking=True
    )
    device.setFan.assert_awaited_with({"speed": 2})

    await hass.services.async_call(
        "fan", "set_preset_mode",
        {"entity_id": "fan.attic_fan", "preset_mode": "Auto"},
        blocking=True,
    )
    device.setFan.assert_awaited_with({"mode": "Auto"})


async def test_fan_turn_on_with_preset_mode(hass, fake_sdk, enable_custom_integrations):
    """turn_on with a preset_mode argument sets the mode without forcing a speed."""
    await setup_entry(hass, device_types=TYPES)
    device = fake_sdk.systemManager.getDeviceById("fan1")

    await hass.services.async_call(
        "fan", "turn_on",
        {"entity_id": "fan.attic_fan", "preset_mode": "Auto"},
        blocking=True,
    )
    device.setFan.assert_awaited_with({"mode": "Auto"})


async def test_fan_turn_on_with_percentage(hass, fake_sdk, enable_custom_integrations):
    """turn_on with a percentage argument sets the speed directly."""
    await setup_entry(hass, device_types=TYPES)
    device = fake_sdk.systemManager.getDeviceById("fan1")

    await hass.services.async_call(
        "fan", "turn_on",
        {"entity_id": "fan.attic_fan", "percentage": 25},
        blocking=True,
    )
    device.setFan.assert_awaited_with({"speed": 1})


async def test_fan_percentage_clamped_when_maxspeed_missing(
    hass, fake_sdk, enable_custom_integrations
):
    """A pushed FanStatus missing maxSpeed (defaults to 1) must not exceed 100%."""
    await setup_entry(hass, device_types=TYPES)

    fake_sdk.systemManager.set_property("fan1", "fan", {"speed": 2})
    await hass.async_block_till_done()

    state = hass.states.get("fan.attic_fan")
    assert state is not None
    assert state.attributes["percentage"] == 100


async def test_fan_turn_on_remembers_speed_from_push_update(
    hass, fake_sdk, enable_custom_integrations
):
    """A push update carrying a non-zero speed is remembered for turn_on."""
    await setup_entry(hass, device_types=TYPES)
    device = fake_sdk.systemManager.getDeviceById("fan1")

    fake_sdk.systemManager.set_property(
        "fan1", "fan",
        {"speed": 3, "maxSpeed": 4, "mode": "Manual", "availableModes": ["Manual", "Auto"]},
    )
    await hass.async_block_till_done()

    await hass.services.async_call(
        "fan", "turn_off", {"entity_id": "fan.attic_fan"}, blocking=True
    )
    device.setFan.assert_awaited_with({"speed": 0})

    fake_sdk.systemManager.set_property(
        "fan1", "fan",
        {"speed": 0, "maxSpeed": 4, "mode": "Manual", "availableModes": ["Manual", "Auto"]},
    )
    await hass.async_block_till_done()

    await hass.services.async_call(
        "fan", "turn_on", {"entity_id": "fan.attic_fan"}, blocking=True
    )
    device.setFan.assert_awaited_with({"speed": 3})
