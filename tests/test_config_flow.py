"""Tests covering the Scrypted config flow."""

from __future__ import annotations

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant import config_entries
from homeassistant.const import (
    CONF_HOST,
    CONF_ICON,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_USERNAME,
)
from homeassistant.data_entry_flow import FlowResultType

from custom_components.scrypted import config_flow
from custom_components.scrypted.const import (
    CONF_AUTO_REGISTER_RESOURCES,
    CONF_SCRYPTED_NVR,
    DOMAIN,
)

CREDENTIALS_INPUT = {
    CONF_HOST: "example",
    CONF_ICON: "mdi:test",
    CONF_NAME: "Scrypted",
    CONF_USERNAME: "user",
    CONF_PASSWORD: "pass",
}


USER_INPUT = {
    **CREDENTIALS_INPUT,
    CONF_SCRYPTED_NVR: True,
    CONF_AUTO_REGISTER_RESOURCES: True,
}


async def test_user_flow_creates_entry(hass):
    """Test case for test_user_flow_creates_entry."""
    init_result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        init_result["flow_id"], USER_INPUT
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == USER_INPUT[CONF_HOST]
    assert result["data"][CONF_AUTO_REGISTER_RESOURCES] is True


async def test_user_flow_invalid_credentials_shows_error(
    hass, mock_retrieve_token_error
):
    """Test case for test_user_flow_invalid_credentials_shows_error."""
    init_result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        init_result["flow_id"], USER_INPUT
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "invalid_host_or_credentials"


async def test_reauth_credentials_invalid_sets_error(hass, mock_retrieve_token_error):
    """Test case for test_reauth_credentials_invalid_sets_error."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "example"})
    entry.add_to_hass(hass)
    context_data = {**entry.data, CONF_PASSWORD: "old"}
    init_result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "data": context_data,
        },
    )
    result = await hass.config_entries.flow.async_configure(
        init_result["flow_id"], CREDENTIALS_INPUT
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "invalid_host_or_credentials"


async def test_reauth_upgrade_defaults_from_context_options(hass):
    """Test case for test_reauth_upgrade_defaults_from_context_options."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "example"},
        options={CONF_AUTO_REGISTER_RESOURCES: True},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "data": entry.data,
            "options": dict(entry.options),
        },
    )
    schema_keys = list(result["data_schema"].schema.keys())
    auto_field = next(
        key for key in schema_keys if key.schema == CONF_AUTO_REGISTER_RESOURCES
    )
    assert auto_field.default() is True


async def test_reauth_without_password_shows_upgrade_step(hass):
    """Test case for test_reauth_without_password_shows_upgrade_step."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "example"})
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "data": entry.data,
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "upgrade"


async def test_reauth_credentials_triggers_reload(hass, mock_async_reload):
    """Test case for test_reauth_credentials_triggers_reload."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "example"})
    entry.add_to_hass(hass)
    context_data = {**entry.data, CONF_PASSWORD: "old"}
    init_result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "data": context_data,
        },
    )
    assert init_result["step_id"] == "credentials"
    result = await hass.config_entries.flow.async_configure(
        init_result["flow_id"], CREDENTIALS_INPUT
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "success"
    mock_async_reload.assert_awaited_once_with(entry.entry_id)


async def test_reauth_duplicate_host_sets_error(hass):
    """Test case for test_reauth_duplicate_host_sets_error."""
    current = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "current"})
    existing = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "example"},
        unique_id="example",
    )
    current.add_to_hass(hass)
    existing.add_to_hass(hass)
    context_data = {**current.data, CONF_PASSWORD: "old"}
    init_result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": current.entry_id,
            "data": context_data,
        },
    )
    result = await hass.config_entries.flow.async_configure(
        init_result["flow_id"], CREDENTIALS_INPUT
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"][CONF_NAME] == "already_configured"


async def test_options_flow_updates_entry(hass):
    """Test case for test_options_flow_updates_entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        options={
            CONF_AUTO_REGISTER_RESOURCES: False,
            CONF_SCRYPTED_NVR: False,
        },
    )
    entry.add_to_hass(hass)
    init_result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        init_result["flow_id"],
        {CONF_AUTO_REGISTER_RESOURCES: True, CONF_SCRYPTED_NVR: True},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_AUTO_REGISTER_RESOURCES] is True
    assert result["data"][CONF_SCRYPTED_NVR] is True


async def test_options_flow_defaults_to_entry_data(hass):
    """Test case for test_options_flow_defaults_to_entry_data."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_AUTO_REGISTER_RESOURCES: True,
            CONF_SCRYPTED_NVR: True,
        },
        options={},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    form_schema = result["data_schema"]
    validated = form_schema({})
    assert validated[CONF_AUTO_REGISTER_RESOURCES] is True
    assert validated[CONF_SCRYPTED_NVR] is True


async def test_options_flow_respects_existing_options(hass):
    """Test case for test_options_flow_respects_existing_options."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        options={
            CONF_AUTO_REGISTER_RESOURCES: False,
            CONF_SCRYPTED_NVR: False,
        },
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    schema_keys = list(result["data_schema"].schema.keys())
    auto_field, nvr_field = schema_keys
    assert auto_field.default() is False
    assert nvr_field.default() is False


async def test_options_flow_init_shows_general_step(hass):
    """Test that initializing the options flow shows the general step."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "example"},
        options={
            CONF_AUTO_REGISTER_RESOURCES: True,
            CONF_SCRYPTED_NVR: False,
        },
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "general"


async def test_options_flow_complete_end_to_end(hass):
    """Test a complete options flow from init to entry creation."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "example",
            CONF_AUTO_REGISTER_RESOURCES: False,
            CONF_SCRYPTED_NVR: False,
        },
        options={},
    )
    entry.add_to_hass(hass)

    # Initialize the options flow
    init_result = await hass.config_entries.options.async_init(entry.entry_id)
    assert init_result["type"] == FlowResultType.FORM
    assert init_result["step_id"] == "general"

    # Configure the options
    result = await hass.config_entries.options.async_configure(
        init_result["flow_id"],
        {CONF_AUTO_REGISTER_RESOURCES: True, CONF_SCRYPTED_NVR: True},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_AUTO_REGISTER_RESOURCES] is True
    assert result["data"][CONF_SCRYPTED_NVR] is True


async def test_validate_input_missing_field_returns_false(hass):
    """Test case for test_validate_input_missing_field_returns_false."""
    flow = config_flow.ScryptedConfigFlow()
    flow.hass = hass
    data = {CONF_HOST: "example", CONF_ICON: "mdi:test"}
    assert await flow.validate_input(data) is False
