"""Config flow for Scrypted integration."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import voluptuous as vol

from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.schema_config_entry_flow import (
    SchemaCommonFlowHandler,
    SchemaConfigFlowHandler,
    SchemaFlowFormStep,
    SchemaFlowMenuStep,
)

from .const import DOMAIN


async def validate_host(
    flow: SchemaCommonFlowHandler, data: dict[str, Any]
) -> dict[str, Any]:
    """Validate that the host is valid."""
    await flow.parent_handler.async_set_unique_id(data[CONF_HOST])
    flow.parent_handler._abort_if_unique_id_configured()
    return data


CONFIG_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.URL)
        ),
    }
)

CONFIG_FLOW: dict[str, SchemaFlowFormStep | SchemaFlowMenuStep] = {
    "user": SchemaFlowFormStep(CONFIG_SCHEMA, validate_user_input=validate_host),
    "import": SchemaFlowFormStep(CONFIG_SCHEMA, validate_user_input=validate_host),
}


class ConfigFlowHandler(SchemaConfigFlowHandler, domain=DOMAIN):
    """Handle a config or options flow for Scrypted."""

    config_flow = CONFIG_FLOW

    @callback
    def async_config_entry_title(self, options: Mapping[str, Any]) -> str:
        """Return config entry title."""
        return cast(str, options[CONF_HOST])
