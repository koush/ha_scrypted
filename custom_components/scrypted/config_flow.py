"""Config flow for Scrypted integration."""

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.const import (
    CONF_HOST,
    CONF_ICON,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_USERNAME,
)
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import slugify

from .const import (
    CONF_AUTO_REGISTER_RESOURCES,
    CONF_SCRYPTED_NVR,
    DOMAIN,
)
from .http import retrieve_token


def text_selector(type: selector.TextSelectorType) -> selector.TextSelector:
    """Create a text selector."""
    return selector.TextSelector(selector.TextSelectorConfig(type=type))


def _get_config_schema(
    default: dict[str, Any] | None,
    *,
    auto_register_default: bool = False,
    include_nvr: bool = False,
    include_auto_register: bool = False,
) -> vol.Schema:
    """Get config schema."""
    if not default:
        default = {}
    auto_register_value = default.get(
        CONF_AUTO_REGISTER_RESOURCES, auto_register_default
    )
    schema: dict[Any, Any] = {
        vol.Required(
            CONF_NAME, default=default.get(CONF_NAME, DOMAIN.title())
        ): text_selector(type=selector.TextSelectorType.TEXT),
        vol.Required(
            CONF_ICON, default=default.get(CONF_ICON, "mdi:memory")
        ): selector.IconSelector(selector.IconSelectorConfig()),
        vol.Required(CONF_HOST, default=default.get(CONF_HOST)): text_selector(
            type=selector.TextSelectorType.TEXT
        ),
        vol.Required(
            CONF_USERNAME, default=default.get(CONF_USERNAME)
        ): text_selector(type=selector.TextSelectorType.TEXT),
        vol.Required(
            CONF_PASSWORD, default=default.get(CONF_PASSWORD)
        ): text_selector(type=selector.TextSelectorType.PASSWORD),
    }
    if include_nvr:
        schema[
            vol.Optional(
                CONF_SCRYPTED_NVR, default=default.get(CONF_SCRYPTED_NVR, False)
            )
        ] = bool
    if include_auto_register:
        schema[
            vol.Required(
                CONF_AUTO_REGISTER_RESOURCES, default=auto_register_value
            )
        ] = bool
    return vol.Schema(schema)


class ScryptedConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a Scrypted config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize flow."""
        self.data = {}

    async def validate_input(self, data: dict[str, Any]) -> bool:
        """Validate that the host is valid."""
        session = async_get_clientsession(self.hass, verify_ssl=False)
        required_keys = [
            CONF_HOST,
            CONF_ICON,
            CONF_NAME,
            CONF_USERNAME,
        ]
        if CONF_AUTO_REGISTER_RESOURCES in data:
            required_keys.append(CONF_AUTO_REGISTER_RESOURCES)
        for key in required_keys:
            if key not in data:
                return False
        try:
            await retrieve_token(data, session)
        except ValueError:
            return False

        return True

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle user flow."""
        errors = {}
        if user_input is not None and CONF_USERNAME in user_input:
            if await self.validate_input(user_input):
                await self.async_set_unique_id(slugify(user_input[CONF_HOST]))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_HOST], data=user_input
                )
            errors["base"] = "invalid_host_or_credentials"

        return self.async_show_form(
            step_id="user",
            data_schema=_get_config_schema(
                user_input,
                auto_register_default=self._async_auto_register_default(user_input),
                include_nvr=True,
                include_auto_register=True,
            ),
            errors=errors,
        )

    async_step_import = async_step_user

    async def async_step_reauth(
        self, _: dict[str, Any] | None
    ) -> config_entries.FlowResult:
        """Handle reauth flow."""
        if CONF_PASSWORD not in self.context["data"]:
            return await self.async_step_upgrade()
        return await self.async_step_credentials()

    async def _async_step_reauth(
        self, step_id: str, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle reauth step."""
        errors = {}
        if user_input is not None:
            if await self.validate_input(user_input):
                unique_id = slugify(user_input[CONF_HOST])
                config_entry = self.hass.config_entries.async_get_entry(
                    self.context["entry_id"]
                )
                assert config_entry
                if not any(
                    entry
                    for entry in self.hass.config_entries.async_entries(DOMAIN)
                    if entry != config_entry and entry.unique_id == unique_id
                ):
                    self.hass.config_entries.async_update_entry(
                        config_entry, data=user_input, options={}, unique_id=unique_id
                    )
                    self.hass.async_create_task(
                        self.hass.config_entries.async_reload(config_entry.entry_id)
                    )
                    return self.async_abort(reason="success")

                errors[CONF_NAME] = "already_configured"

            if not errors:
                errors["base"] = "invalid_host_or_credentials"

        defaults = user_input or self.context["data"]
        include_auto = step_id != "credentials"
        include_nvr = step_id != "credentials"

        return self.async_show_form(
            step_id=step_id,
            data_schema=_get_config_schema(
                defaults,
                auto_register_default=self._async_auto_register_default(defaults),
                include_nvr=include_nvr,
                include_auto_register=include_auto,
            ),
            errors=errors,
        )

    async def async_step_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle credentials step."""
        return await self._async_step_reauth("credentials", user_input)

    async def async_step_upgrade(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle upgrade step."""
        return await self._async_step_reauth("upgrade", user_input)

    def _async_auto_register_default(
        self, data: dict[str, Any] | None
    ) -> bool:
        """Determine the auto register default."""
        if data and CONF_AUTO_REGISTER_RESOURCES in data:
            return data[CONF_AUTO_REGISTER_RESOURCES]
        if options := self.context.get("options"):
            return options.get(CONF_AUTO_REGISTER_RESOURCES, False)
        return False


    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow handler for this config entry."""
        return ScryptedOptionsFlowHandler()


class ScryptedOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Scrypted options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Initialize the options flow."""
        return await self.async_step_general(user_input)

    async def async_step_general(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle general options."""
        if user_input is not None:
            data = {
                **self.config_entry.options,
                CONF_AUTO_REGISTER_RESOURCES: user_input[
                    CONF_AUTO_REGISTER_RESOURCES
                ],
                CONF_SCRYPTED_NVR: user_input[CONF_SCRYPTED_NVR],
            }
            return self.async_create_entry(data=data)

        current_auto = self.config_entry.options.get(
            CONF_AUTO_REGISTER_RESOURCES
        )
        if current_auto is None:
            current_auto = self.config_entry.data.get(
                CONF_AUTO_REGISTER_RESOURCES, False
            )

        current_nvr = self.config_entry.options.get(CONF_SCRYPTED_NVR)
        if current_nvr is None:
            current_nvr = self.config_entry.data.get(
                CONF_SCRYPTED_NVR, False
            )

        return self.async_show_form(
            step_id="general",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_AUTO_REGISTER_RESOURCES, default=current_auto
                    ): bool,
                    vol.Required(CONF_SCRYPTED_NVR, default=current_nvr): bool,
                }
            ),
        )
