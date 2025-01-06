"""The Scrypted integration."""
from __future__ import annotations

from aiohttp import ClientConnectorError

from typing import Any

from homeassistant.components.frontend import (
    async_register_built_in_panel,
    async_remove_panel,
)
from homeassistant.components.persistent_notification import async_create
from homeassistant.config_entries import SOURCE_IMPORT, SOURCE_REAUTH, ConfigEntry
from homeassistant.const import CONF_ICON, CONF_NAME, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .http import ScryptedView, retrieve_token

from homeassistant.components import panel_custom, websocket_api


PLATFORMS = [
    Platform.SENSOR
]

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Auth setup."""
    session = async_get_clientsession(hass, verify_ssl=False)
    hass.http.register_view(ScryptedView(hass, session))

    if DOMAIN in config:
        async_create(
            hass,
            (
                "Your Scrypted configuration has been imported as a config entry and "
                "can safely be removed from your configuration.yaml."
            ),
            "Scrypted Config Import",
        )
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": SOURCE_IMPORT}, data=config[DOMAIN]
            )
        )
        return False
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up a Scrypted config entry."""

    @callback
    def _reauth(data: dict[str, Any]) -> bool:
        """Start Reauth flow."""
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={
                    "source": SOURCE_REAUTH,
                    "entry_id": config_entry.entry_id,
                    "data": dict(data),
                },
            )
        )
        return False

    if not config_entry.data:
        return _reauth(config_entry.options)

    session = async_get_clientsession(hass, verify_ssl=False)
    try:
        if not (token := await retrieve_token(config_entry.data, session)):
            return _reauth(config_entry.data)
    except Exception as e:
        if isinstance(e, ClientConnectorError):
            raise ConfigEntryNotReady("ClientConnectorError. Is the Scrypted host down? Retrying.")
        raise e

    hass.data.setdefault(DOMAIN, {})[token] = config_entry

    custom_panel_config = {
        "name": "ha-panel-scrypted",
        # "embed_iframe": True,
        "trust_external": False,
        "module_url": f"/api/{DOMAIN}/{token}/entrypoint.js",
    }

    panelconf = {}
    panelconf["_panel_custom"] = custom_panel_config
    panelconf["version"] = "1.0.0"

    async_register_built_in_panel(
        hass,
        "custom",
        config_entry.data[CONF_NAME],
        config_entry.data[CONF_ICON],
        f"{DOMAIN}_{token}",
        panelconf,
        require_admin=False,
    )

    # Set up token sensor
    await hass.config_entries.async_forward_entry_setups(
        config_entry, PLATFORMS
    )
    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    token = next(
        token
        for token, entry in hass.data[DOMAIN].items()
        if entry.entry_id == config_entry.entry_id
    )
    hass.data[DOMAIN].pop(token)
    if not hass.data[DOMAIN]:
        hass.data.pop(DOMAIN)
    async_remove_panel(hass, f"{DOMAIN}_{config_entry.entry_id}")
    return True
