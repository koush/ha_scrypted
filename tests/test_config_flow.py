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
    CONF_ENABLE_ENTITIES,
    CONF_EXCLUDED_PLUGINS,
    CONF_SCRYPTED_NVR,
    DOMAIN,
)
from tests.conftest import setup_entry, state
from tests.const import EXAMPLE_HOST, PASSWORD, USERNAME

CREDENTIALS_INPUT = {
    CONF_HOST: EXAMPLE_HOST,
    CONF_ICON: "mdi:test",
    CONF_NAME: "Scrypted",
    CONF_USERNAME: USERNAME,
    CONF_PASSWORD: PASSWORD,
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
    # Entry setup schedules a reload while migrating options; let it finish so
    # the test does not leave a lingering task behind.
    await hass.async_block_till_done()


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
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: EXAMPLE_HOST})
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
        data={CONF_HOST: EXAMPLE_HOST},
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
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: EXAMPLE_HOST})
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
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: EXAMPLE_HOST})
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
        data={CONF_HOST: EXAMPLE_HOST},
        unique_id=EXAMPLE_HOST,
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
    auto_field, nvr_field, entities_field, types_field, plugins_field = schema_keys
    assert auto_field.default() is False
    assert nvr_field.default() is False
    assert entities_field.default() is True
    assert types_field.default() == ["Camera", "Doorbell"]
    assert plugins_field.default() == []


async def test_options_flow_init_shows_general_step(hass):
    """Test that initializing the options flow shows the general step."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: EXAMPLE_HOST},
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
            CONF_HOST: EXAMPLE_HOST,
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
    data = {CONF_HOST: EXAMPLE_HOST, CONF_ICON: "mdi:test"}
    assert await flow.validate_input(data) is False


async def test_options_flow_includes_enable_entities(hass):
    """Options flow exposes and persists the enable_entities flag."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "host": "1.2.3.4",
            "username": "u",
            "password": "p",
            "name": "Scrypted",
            "icon": "mdi:memory",
        },
        options={
            CONF_AUTO_REGISTER_RESOURCES: False,
            CONF_SCRYPTED_NVR: False,
            CONF_ENABLE_ENTITIES: True,
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "form"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_AUTO_REGISTER_RESOURCES: False,
            CONF_SCRYPTED_NVR: False,
            CONF_ENABLE_ENTITIES: False,
            "device_types": ["Camera", "Doorbell"],
        },
    )
    assert result["type"] == "create_entry"
    assert result["data"][CONF_ENABLE_ENTITIES] is False


async def test_reauth_preserves_entity_options(hass):
    """Reauth keeps options its form never collects."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: EXAMPLE_HOST},
        options={
            CONF_AUTO_REGISTER_RESOURCES: False,
            CONF_SCRYPTED_NVR: False,
            CONF_ENABLE_ENTITIES: False,
            "device_types": ["Camera", "Doorbell", "Sensor"],
        },
    )
    entry.add_to_hass(hass)

    init_result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "data": {**entry.data, CONF_PASSWORD: "old"},
        },
    )
    result = await hass.config_entries.flow.async_configure(
        init_result["flow_id"], CREDENTIALS_INPUT
    )
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.ABORT
    assert entry.options["device_types"] == ["Camera", "Doorbell", "Sensor"]
    assert entry.options[CONF_ENABLE_ENTITIES] is False


async def test_upgrade_step_applies_its_own_fields_and_keeps_the_rest(hass):
    """The upgrade form's own fields win; entity options survive."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: EXAMPLE_HOST},
        options={
            CONF_AUTO_REGISTER_RESOURCES: False,
            CONF_SCRYPTED_NVR: False,
            CONF_ENABLE_ENTITIES: False,
            "device_types": ["Camera", "Doorbell", "Sensor"],
        },
    )
    entry.add_to_hass(hass)

    init_result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
            "data": entry.data,
        },
    )
    assert init_result["step_id"] == "upgrade"
    result = await hass.config_entries.flow.async_configure(
        init_result["flow_id"], USER_INPUT
    )
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.ABORT
    # USER_INPUT turns both of these on.
    assert entry.options[CONF_SCRYPTED_NVR] is True
    assert entry.options[CONF_AUTO_REGISTER_RESOURCES] is True
    # Untouched by this form.
    assert entry.options[CONF_ENABLE_ENTITIES] is False
    assert entry.options["device_types"] == ["Camera", "Doorbell", "Sensor"]


def _excluded_plugins_field(result):
    """Return (schema key, selector) for the excluded plugins option."""
    for key, selector in result["data_schema"].schema.items():
        if key == CONF_EXCLUDED_PLUGINS:
            return key, selector
    raise AssertionError("excluded_plugins field missing")


async def test_options_flow_lists_plugins_from_live_server(
    hass, fake_sdk, enable_custom_integrations
):
    """The plugin choices are live plugins that own user-facing devices."""
    devices = {
        # Owns a user-facing device: offered, labelled by its plugin device.
        "ring_plugin": state(
            name="Ring Plugin",
            type="API",
            info={},
            pluginId="@scrypted/ring",
            interfaces=["ScryptedPlugin"],
        ),
        "ring1": state(
            name="Hall Leak",
            type="Sensor",
            info={},
            pluginId="@scrypted/ring",
            interfaces=["FloodSensor"],
        ),
        # Owns only a type the options never offer: not offered.
        "llm_tools": state(
            name="Web Tools",
            type="LLMTools",
            info={},
            pluginId="@scrypted/llm",
            interfaces=["LLMTools"],
        ),
        # Owns only plumbing: not offered.
        "webrtc_plugin": state(
            name="WebRTC Plugin",
            type="API",
            info={},
            pluginId="@scrypted/webrtc",
            interfaces=["ScryptedPlugin"],
        ),
    }
    fake_sdk.systemManager.systemState.update(devices)
    entry = await setup_entry(hass)
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_EXCLUDED_PLUGINS: ["@scrypted/gone"]}
    )
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    key, selector = _excluded_plugins_field(result)
    assert key.default() == ["@scrypted/gone"]
    # @scrypted/homeassistant (haimport1) is always excluded, so never offered;
    # a saved plugin the server no longer has stays selectable.
    assert selector.config["options"] == [
        {"value": "@scrypted/gone", "label": "@scrypted/gone"},
        {"value": "@scrypted/ring", "label": "Ring Plugin (@scrypted/ring)"},
    ]
    assert selector.config["custom_value"] is True

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_AUTO_REGISTER_RESOURCES: False,
            CONF_SCRYPTED_NVR: False,
            CONF_ENABLE_ENTITIES: True,
            "device_types": ["Camera", "Doorbell", "Sensor"],
            CONF_EXCLUDED_PLUGINS: ["@scrypted/ring"],
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_EXCLUDED_PLUGINS] == ["@scrypted/ring"]


async def test_options_flow_plugins_without_connection(hass):
    """Without a live connection the saved plugins remain selectable."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        options={CONF_EXCLUDED_PLUGINS: ["@scrypted/ring"]},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    key, selector = _excluded_plugins_field(result)
    assert key.default() == ["@scrypted/ring"]
    assert selector.config["options"] == [
        {"value": "@scrypted/ring", "label": "@scrypted/ring"}
    ]
