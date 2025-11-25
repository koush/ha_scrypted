from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.scrypted import config_flow
from custom_components.scrypted.const import (
    CONF_AUTO_REGISTER_RESOURCES,
    CONF_SCRYPTED_NVR,
    DOMAIN,
)
from homeassistant.const import (
    CONF_HOST,
    CONF_ICON,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_USERNAME,
)

from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.mark.asyncio
async def test_validate_input_accepts_complete_data(hass):
    flow = config_flow.ScryptedConfigFlow()
    flow.hass = hass
    data = {
        CONF_HOST: "example",
        CONF_ICON: "mdi:test",
        CONF_NAME: "Scrypted",
        CONF_USERNAME: "user",
        CONF_PASSWORD: "pass",
        CONF_AUTO_REGISTER_RESOURCES: True,
    }
    assert await flow.validate_input(data) is True


@pytest.mark.asyncio
async def test_validate_input_missing_field_returns_false(hass):
    flow = config_flow.ScryptedConfigFlow()
    flow.hass = hass
    data = {CONF_HOST: "example", CONF_ICON: "mdi:test"}
    assert await flow.validate_input(data) is False


@pytest.mark.asyncio
async def test_async_step_user_success(hass):
    flow = config_flow.ScryptedConfigFlow()
    flow.hass = hass
    flow.context = {}
    user_input = {
        CONF_HOST: "example",
        CONF_ICON: "mdi:test",
        CONF_NAME: "Scrypted",
        CONF_USERNAME: "user",
        CONF_PASSWORD: "pass",
        CONF_SCRYPTED_NVR: True,
        CONF_AUTO_REGISTER_RESOURCES: True,
    }
    result = await flow.async_step_user(user_input)
    assert result["type"] == "create_entry"
    assert result["title"] == "example"


@pytest.mark.asyncio
async def test_async_step_user_invalid(hass, monkeypatch):
    flow = config_flow.ScryptedConfigFlow()
    flow.hass = hass
    flow.context = {}

    async def _reject(*args, **kwargs):
        return False

    monkeypatch.setattr(flow, "validate_input", _reject)
    result = await flow.async_step_user(
        {
            CONF_HOST: "example",
            CONF_ICON: "mdi:test",
            CONF_NAME: "Scrypted",
            CONF_USERNAME: "user",
            CONF_PASSWORD: "pass",
        }
    )
    assert result["type"] == "form"
    assert result["errors"]["base"] == "invalid_host_or_credentials"


@pytest.mark.asyncio
async def test_async_step_reauth_without_password_goes_to_upgrade(hass):
    flow = config_flow.ScryptedConfigFlow()
    flow.hass = hass
    flow.context = {"data": {CONF_HOST: "example"}}
    result = await flow.async_step_reauth({})
    assert result["step_id"] == "upgrade"


@pytest.mark.asyncio
async def test_async_step_credentials_triggers_reload(hass, monkeypatch):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "example"})
    entry.add_to_hass(hass)
    reload_mock = AsyncMock()
    monkeypatch.setattr(hass.config_entries, "async_reload", reload_mock)
    flow = config_flow.ScryptedConfigFlow()
    flow.hass = hass
    flow.context = {"entry_id": entry.entry_id, "data": entry.data}
    result = await flow.async_step_credentials(
        {
            CONF_HOST: "example",
            CONF_ICON: "mdi:test",
            CONF_NAME: "Scrypted",
            CONF_USERNAME: "user",
            CONF_PASSWORD: "pass",
            CONF_AUTO_REGISTER_RESOURCES: False,
            CONF_SCRYPTED_NVR: False,
        }
    )
    await hass.async_block_till_done()
    assert result["type"] == "abort"
    assert result["reason"] == "success"
    reload_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_step_credentials_duplicate_host_sets_error(hass):
    current = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "current"})
    existing = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "example"}, unique_id="example")
    current.add_to_hass(hass)
    existing.add_to_hass(hass)
    flow = config_flow.ScryptedConfigFlow()
    flow.hass = hass
    flow.context = {"entry_id": current.entry_id, "data": current.data}
    result = await flow.async_step_credentials(
        {
            CONF_HOST: "example",
            CONF_ICON: "mdi:test",
            CONF_NAME: "Scrypted",
            CONF_USERNAME: "user",
            CONF_PASSWORD: "pass",
        }
    )
    assert result["errors"][CONF_NAME] == "already_configured"


def test_auto_register_default_uses_context_options():
    flow = config_flow.ScryptedConfigFlow()
    flow.context = {"options": {CONF_AUTO_REGISTER_RESOURCES: True}}
    assert flow._async_auto_register_default({}) is True
    assert (
        flow._async_auto_register_default({CONF_AUTO_REGISTER_RESOURCES: False})
        is False
    )


@pytest.mark.asyncio
async def test_options_flow_updates_entry(hass, monkeypatch):
    entry = MockConfigEntry(domain=DOMAIN, options={CONF_AUTO_REGISTER_RESOURCES: False})
    handler = config_flow.ScryptedOptionsFlowHandler(entry)
    handler.hass = hass
    reload_mock = AsyncMock()
    monkeypatch.setattr(hass.config_entries, "async_reload", reload_mock)
    result = await handler.async_step_general({CONF_AUTO_REGISTER_RESOURCES: True})
    await hass.async_block_till_done()
    assert result["type"] == "create_entry"
    assert result["data"][CONF_AUTO_REGISTER_RESOURCES] is True
    reload_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_options_flow_defaults_to_entry_data(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_AUTO_REGISTER_RESOURCES: True},
        options={},
    )
    handler = config_flow.ScryptedOptionsFlowHandler(entry)
    handler.hass = hass
    result = await handler.async_step_general(None)
    form_schema = result["data_schema"]
    validated = form_schema({})
    assert validated[CONF_AUTO_REGISTER_RESOURCES] is True

def test_get_config_schema_handles_none_defaults():
    schema = config_flow._get_config_schema(None, include_auto_register=True)
    assert callable(schema)


@pytest.mark.asyncio
async def test_validate_input_returns_false_on_value_error(hass, monkeypatch):
    flow = config_flow.ScryptedConfigFlow()
    flow.hass = hass

    async def _raise(*args, **kwargs):
        raise ValueError

    monkeypatch.setattr(config_flow, "retrieve_token", _raise)
    data = {
        CONF_HOST: "example",
        CONF_ICON: "mdi:test",
        CONF_NAME: "Scrypted",
        CONF_USERNAME: "user",
        CONF_PASSWORD: "pass",
    }
    assert await flow.validate_input(data) is False


@pytest.mark.asyncio
async def test_async_step_reauth_calls_credentials_when_password_present(hass, monkeypatch):
    flow = config_flow.ScryptedConfigFlow()
    flow.hass = hass
    flow.context = {"data": {CONF_PASSWORD: "pw"}}
    creds = AsyncMock(return_value={"type": "test"})
    monkeypatch.setattr(flow, "async_step_credentials", creds)
    result = await flow.async_step_reauth(None)
    assert result == {"type": "test"}
    creds.assert_awaited_once()


@pytest.mark.asyncio
async def test__async_step_reauth_sets_base_error(hass, monkeypatch):
    flow = config_flow.ScryptedConfigFlow()
    flow.hass = hass
    flow.context = {"entry_id": "entry", "data": {CONF_HOST: "example"}}

    async def _reject(*args, **kwargs):
        return False

    monkeypatch.setattr(flow, "validate_input", _reject)
    result = await flow._async_step_reauth("upgrade", {CONF_HOST: "example"})
    assert result["errors"]["base"] == "invalid_host_or_credentials"


@pytest.mark.asyncio
async def test_options_flow_init_delegates_to_general(hass, monkeypatch):
    entry = MockConfigEntry(domain=DOMAIN)
    handler = config_flow.ScryptedOptionsFlowHandler(entry)
    handler.hass = hass
    general = AsyncMock(return_value={"type": "form"})
    monkeypatch.setattr(handler, "async_step_general", general)
    result = await handler.async_step_init(None)
    assert result == {"type": "form"}
    general.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_get_options_flow_returns_handler(hass):
    entry = MockConfigEntry(domain=DOMAIN)
    handler = await config_flow.async_get_options_flow(entry)
    assert isinstance(handler, config_flow.ScryptedOptionsFlowHandler)
