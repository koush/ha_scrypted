"""The Scrypted integration."""

from dataclasses import dataclass
import logging
from typing import Any

from aiohttp import ClientConnectorError, ClientResponseError
from scrypted_sdk import ScryptedConnectionError

from homeassistant.components.frontend import (
    async_register_built_in_panel,
    async_remove_panel,
)
from homeassistant.components.lovelace.const import (
    CONF_RESOURCE_TYPE_WS,
    DOMAIN as LL_DOMAIN,
)
from homeassistant.components.lovelace.resources import (
    ResourceStorageCollection,
    ResourceYAMLCollection,
)
from homeassistant.components.persistent_notification import async_create
from homeassistant.config_entries import SOURCE_IMPORT, SOURCE_REAUTH, ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_ICON,
    CONF_ID,
    CONF_NAME,
    CONF_URL,
    Platform,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_AUTO_REGISTER_RESOURCES,
    CONF_DEVICE_TYPES,
    CONF_ENABLE_ENTITIES,
    CONF_SCRYPTED_NVR,
    DEFAULT_DEVICE_TYPES,
    DOMAIN,
)
from .entity import exposed_device
from .http import ScryptedView, retrieve_token
from .hub import ScryptedClient
from .sdk import get_base_url


@dataclass
class ScryptedRuntimeData:
    """Objects for this config entry's lifetime."""

    token: str
    client: ScryptedClient | None


PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.CAMERA,
    Platform.CLIMATE,
    Platform.COVER,
    Platform.EVENT,
    Platform.FAN,
    Platform.LIGHT,
    Platform.LOCK,
    Platform.MEDIA_PLAYER,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.VACUUM,
]

_LOGGER = logging.getLogger(__name__)
_RESOURCE_TRACKER = f"{DOMAIN}_lovelace_resources"
_OPTION_DEFAULTS = {
    CONF_AUTO_REGISTER_RESOURCES: False,
    CONF_SCRYPTED_NVR: False,
    CONF_ENABLE_ENTITIES: True,
    CONF_DEVICE_TYPES: DEFAULT_DEVICE_TYPES,
}


def _get_card_resource_definitions(token: str) -> list[tuple[str, str]]:
    """Return the Lovelace resources that power the Scrypted cards."""
    base_url = f"/api/{DOMAIN}/{token}/endpoint/@scrypted/nvr/assets/web-components"
    return [
        ("module", f"{base_url}.js"),
        ("css", f"{base_url}.css"),
    ]


async def _async_register_lovelace_resource(
    hass: HomeAssistant, token: str, entry_id: str
) -> None:
    """Register the Lovelace resources used by the custom cards.

    We inspect the current Lovelace storage collection and only create entries for URLs
    that are missing. When an entry is auto-created we remember which URLs belong to the
    config entry so a later unload can tear down exactly the resources the integration added.
    """
    lovelace_data = hass.data.get(LL_DOMAIN)
    if not lovelace_data or not lovelace_data.resources:
        return

    resources: ResourceStorageCollection | ResourceYAMLCollection = (
        lovelace_data.resources
    )
    if not resources.loaded:
        await resources.async_load()
        resources.loaded = True

    # Keep track of which URLs we created so we can cleanly undo only those later.
    tracker: dict[str, set[str]] = hass.data.setdefault(_RESOURCE_TRACKER, {})
    entry_tracker = tracker.setdefault(entry_id, set())

    for resource_type, resource_url in _get_card_resource_definitions(token):
        # Skip creation when Home Assistant already has an entry for this URL.
        try:
            resource_id = next(
                data.get(CONF_ID)
                for data in resources.async_items()
                if data[CONF_URL] == resource_url
            )
        except StopIteration:
            if isinstance(resources, ResourceYAMLCollection):
                _LOGGER.warning(
                    "Scrypted Lovelace resource can't automatically be registered "
                    "because this Home Assistant instance manages resources via YAML. "
                    "Please register the following resource manually:\n"
                    "  - url: %s\n    type: %s",
                    resource_url,
                    resource_type,
                )
                continue

            data = await resources.async_create_item(
                {CONF_RESOURCE_TYPE_WS: resource_type, CONF_URL: resource_url}
            )
            entry_tracker.add(resource_url)
            _LOGGER.debug(
                "Registered Scrypted Lovelace resource (resource ID %s) for entry %s",
                data.get(CONF_ID),
                entry_id,
            )
        else:
            _LOGGER.debug(
                "Scrypted Lovelace resource already registered with resource ID %s",
                resource_id,
            )

    if not entry_tracker:
        tracker.pop(entry_id, None)
    if not tracker:
        hass.data.pop(_RESOURCE_TRACKER, None)


async def _async_unregister_lovelace_resource(
    hass: HomeAssistant, entry_id: str
) -> None:
    """Remove any Lovelace resources created for this entry.

    During unload we look up the URLs that were created while the entry was active and
    remove only those resources, leaving any manually registered URLs intact.
    """
    tracker: dict[str, set[str]] | None = hass.data.get(_RESOURCE_TRACKER)
    if not tracker or entry_id not in tracker:
        return

    tracked_urls = tracker.pop(entry_id)
    if not tracked_urls:
        if not tracker:
            hass.data.pop(_RESOURCE_TRACKER, None)
        return

    lovelace_data = hass.data.get(LL_DOMAIN)
    if not lovelace_data or not lovelace_data.resources:
        if not tracker:
            hass.data.pop(_RESOURCE_TRACKER, None)
        return

    resources: ResourceStorageCollection | ResourceYAMLCollection = (
        lovelace_data.resources
    )
    if not resources.loaded:
        await resources.async_load()
        resources.loaded = True

    for resource_url in tracked_urls:
        # Only delete resources that are still present and managed via storage.
        try:
            resource_id = next(
                data.get(CONF_ID)
                for data in resources.async_items()
                if data[CONF_URL] == resource_url
            )
        except StopIteration:
            _LOGGER.debug(
                "Scrypted resource %s was not found while unloading entry %s",
                resource_url,
                entry_id,
            )
            continue

        if isinstance(resources, ResourceYAMLCollection):
            _LOGGER.debug(
                "Resources switched to YAML mode after registration, skipping automatic removal for %s",
                resource_url,
            )
            continue

        await resources.async_delete_item(resource_id)
        _LOGGER.debug(
            "Removed Scrypted Lovelace resource (resource ID %s) for entry %s",
            resource_id,
            entry_id,
        )

    if not tracker:
        hass.data.pop(_RESOURCE_TRACKER, None)


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
        payload = {**config_entry.data, **config_entry.options, **data}
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={
                    "source": SOURCE_REAUTH,
                    "entry_id": config_entry.entry_id,
                    "data": payload,
                    "options": dict(config_entry.options),
                },
            )
        )
        return False

    if not config_entry.data:
        return _reauth(config_entry.options)

    changed = await _async_ensure_entry_options(hass, config_entry)
    if changed:
        hass.async_create_task(hass.config_entries.async_reload(config_entry.entry_id))
        return False

    session = async_get_clientsession(hass, verify_ssl=False)
    try:
        if not (token := await retrieve_token(config_entry.data, session)):
            return _reauth(config_entry.data)
    except Exception as e:
        if isinstance(e, ClientConnectorError):
            raise ConfigEntryNotReady(
                "ClientConnectorError. Is the Scrypted host down? Retrying."
            )
        if isinstance(e, ClientResponseError) and e.status in (401, 403):
            _LOGGER.warning(
                "Scrypted authentication failed (HTTP %s) for %s; starting reauth flow.",
                e.status,
                config_entry.title,
            )
            return _reauth(config_entry.data)
        raise e

    config_entry.async_on_unload(
        config_entry.add_update_listener(_async_update_listener)
    )

    client: ScryptedClient | None = None
    if config_entry.options.get(CONF_ENABLE_ENTITIES, True):
        client = ScryptedClient(hass, config_entry)
        try:
            await client.async_connect()
        except ScryptedConnectionError as err:
            # Token retrieval succeeded so the server is up; engine.io failing
            # is unexpected — retry the whole entry setup.
            raise ConfigEntryNotReady(
                f"Scrypted engine.io connect failed: {err}"
            ) from err

        device_registry = dr.async_get(hass)
        device_registry.async_get_or_create(
            config_entry_id=config_entry.entry_id,
            identifiers={(DOMAIN, config_entry.entry_id)},
            manufacturer="Scrypted",
            name=config_entry.data[CONF_NAME],
            configuration_url=get_base_url(config_entry.data[CONF_HOST]),
        )

    # Published only once setup can no longer fail: the proxy view and the
    # token sensor resolve entries through this mapping, and a failed setup
    # never reaches async_unload_entry to clean it up again.
    hass.data.setdefault(DOMAIN, {})[token] = config_entry
    config_entry.runtime_data = ScryptedRuntimeData(token=token, client=client)

    if config_entry.options.get(CONF_AUTO_REGISTER_RESOURCES):
        await _async_register_lovelace_resource(hass, token, config_entry.entry_id)

    custom_panel_config = {
        "name": "ha-panel-scrypted",
        # "embed_iframe": True,
        "trust_external": False,
        # The panel sizes itself against the viewport, so it has to own the
        # safe-area insets too. Without this HA also pads the panel container
        # and the two disagree, pushing the bottom of the iframe off-screen.
        "handle_safe_area": True,
        "module_url": f"/api/{DOMAIN}/{token}/entrypoint.js",
    }

    panel_conf = {
        "_panel_custom": custom_panel_config,
        "version": "1.0.0",
    }

    async_register_built_in_panel(
        hass,
        "custom",
        sidebar_title=config_entry.data[CONF_NAME],
        sidebar_icon=config_entry.data[CONF_ICON],
        frontend_url_path=f"{DOMAIN}_{token}",
        config=panel_conf,
        require_admin=False,
    )

    # Set up token sensor
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)
    return True


async def async_remove_config_entry_device(
    hass: HomeAssistant, config_entry: ConfigEntry, device_entry: dr.DeviceEntry
) -> bool:
    """Allow removing a device from the UI once scrypted stops exposing it.

    The hub device and any device that would still produce entities (present
    in the scrypted system state with an allowlisted type) stay protected.
    """
    # HA offers device removal regardless of entry state, and runtime_data only
    # exists while the entry is loaded.
    data = getattr(config_entry, "runtime_data", None)
    client = data.client if data else None
    prefix = f"{config_entry.entry_id}_"

    for domain, identifier in device_entry.identifiers:
        if domain != DOMAIN:
            continue
        if identifier == config_entry.entry_id:
            # The hub device representing the scrypted server itself.
            return False
        if not identifier.startswith(prefix):
            continue
        if exposed_device(client, identifier.removeprefix(prefix)) is not None:
            # Still exposed by the integration; deleting it would only have
            # it reappear on the next event or reload.
            return False
    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        config_entry, PLATFORMS
    )
    if not unload_ok:
        return False

    if (data := getattr(config_entry, "runtime_data", None)) and data.client:
        await data.client.async_disconnect()

    token = next(
        token
        for token, entry in hass.data[DOMAIN].items()
        if entry.entry_id == config_entry.entry_id
    )

    await _async_unregister_lovelace_resource(hass, config_entry.entry_id)

    hass.data[DOMAIN].pop(token)
    if not hass.data[DOMAIN]:
        hass.data.pop(DOMAIN)
    async_remove_panel(hass, f"{DOMAIN}_{token}")
    return True


async def _async_update_listener(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> None:
    """Ensure option keys stay in the options dict and reload on change."""
    await _async_ensure_entry_options(hass, config_entry)
    hass.async_create_task(hass.config_entries.async_reload(config_entry.entry_id))


async def _async_ensure_entry_options(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> bool:
    """Move option fields into options and ensure defaults exist."""
    data = dict(config_entry.data)
    options = dict(config_entry.options)
    changed = False

    for key, default in _OPTION_DEFAULTS.items():
        if key in data:
            if key not in options:
                options[key] = data[key]
            data.pop(key)
            changed = True

        if key not in options:
            options[key] = default
            changed = True

    if changed:
        hass.config_entries.async_update_entry(config_entry, data=data, options=options)

    return changed
