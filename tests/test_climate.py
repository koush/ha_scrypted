"""Tests for scrypted thermostats."""
from tests.test_binary_sensor import setup_entry

TYPES = ["Camera", "Doorbell", "Thermostat"]


async def test_thermostat_discovered_with_state(hass, fake_sdk, enable_custom_integrations):
    await setup_entry(hass, device_types=TYPES)
    state = hass.states.get("climate.hallway_thermostat")
    assert state is not None
    assert state.state == "heat"
    assert state.attributes["hvac_modes"] == ["off", "heat", "cool", "heat_cool"]
    assert state.attributes["hvac_action"] == "heating"
    assert state.attributes["temperature"] == 21
    assert state.attributes["current_temperature"] == 20
    assert state.attributes["current_humidity"] == 40


async def test_thermostat_range_setpoint(hass, fake_sdk, enable_custom_integrations):
    fake_sdk.systemManager.systemState["thermo1"]["temperatureSetting"] = {
        "value": {
            "availableModes": ["Off", "HeatCool"],
            "mode": "HeatCool",
            "activeMode": "Cool",
            "setpoint": [19, 24],
        }
    }
    await setup_entry(hass, device_types=TYPES)
    state = hass.states.get("climate.hallway_thermostat")
    assert state.attributes["target_temp_low"] == 19
    assert state.attributes["target_temp_high"] == 24
    assert state.attributes["hvac_action"] == "cooling"


async def test_thermostat_commands(hass, fake_sdk, enable_custom_integrations):
    await setup_entry(hass, device_types=TYPES)
    device = fake_sdk.systemManager.getDeviceById("thermo1")

    await hass.services.async_call(
        "climate", "set_temperature",
        {"entity_id": "climate.hallway_thermostat", "temperature": 22.5},
        blocking=True,
    )
    device.setTemperature.assert_awaited_with({"setpoint": 22.5})

    await hass.services.async_call(
        "climate", "set_hvac_mode",
        {"entity_id": "climate.hallway_thermostat", "hvac_mode": "cool"},
        blocking=True,
    )
    device.setTemperature.assert_awaited_with({"mode": "Cool"})


async def test_thermostat_turn_off(hass, fake_sdk, enable_custom_integrations):
    await setup_entry(hass, device_types=TYPES)
    device = fake_sdk.systemManager.getDeviceById("thermo1")

    await hass.services.async_call(
        "climate", "turn_off",
        {"entity_id": "climate.hallway_thermostat"},
        blocking=True,
    )
    device.setTemperature.assert_awaited_with({"mode": "Off"})


async def test_thermostat_set_temperature_with_hvac_mode(
    hass, fake_sdk, enable_custom_integrations
):
    await setup_entry(hass, device_types=TYPES)
    device = fake_sdk.systemManager.getDeviceById("thermo1")

    entity = hass.data["entity_components"]["climate"].get_entity(
        "climate.hallway_thermostat"
    )
    await entity.async_set_temperature(temperature=23, hvac_mode="cool")
    device.setTemperature.assert_awaited_with({"setpoint": 23, "mode": "Cool"})

    device.setTemperature.reset_mock()
    await entity.async_set_temperature()
    device.setTemperature.assert_not_awaited()


async def test_thermostat_range_command(hass, fake_sdk, enable_custom_integrations):
    fake_sdk.systemManager.systemState["thermo1"]["temperatureSetting"] = {
        "value": {
            "availableModes": ["Off", "HeatCool"],
            "mode": "HeatCool",
            "setpoint": [19, 24],
        }
    }
    await setup_entry(hass, device_types=TYPES)
    device = fake_sdk.systemManager.getDeviceById("thermo1")
    await hass.services.async_call(
        "climate", "set_temperature",
        {
            "entity_id": "climate.hallway_thermostat",
            "target_temp_low": 18,
            "target_temp_high": 25,
        },
        blocking=True,
    )
    device.setTemperature.assert_awaited_with({"setpoint": [18, 25]})
