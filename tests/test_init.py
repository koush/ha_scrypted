"""Tests for the Scrypted integration setup logic."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp import ClientResponseError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from scrypted_sdk import ScryptedConnectionError

from homeassistant.components.lovelace.const import DOMAIN as LL_DOMAIN
from homeassistant.components.lovelace.resources import (
    ResourceStorageCollection,
    ResourceYAMLCollection,
)
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import (
    CONF_HOST,
    CONF_ICON,
    CONF_ID,
    CONF_NAME,
    CONF_URL,
    CONF_USERNAME,
)
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from custom_components import scrypted
from custom_components.scrypted.const import (
    CONF_AUTO_REGISTER_RESOURCES,
    CONF_ENABLE_ENTITIES,
    CONF_SCRYPTED_NVR,
    DOMAIN,
)
from tests.conftest import setup_entry
from tests.const import EXAMPLE_HOST


class FakeStorageResources(ResourceStorageCollection):
    """Storage-backed fake resources used in tests."""

    def __init__(self, items: list[dict] | None = None) -> None:
        self._items = list(items or [])
        self.loaded = False
        self.created: list[dict] = []
        self.deleted: list[int] = []

    async def async_load(self):
        self.loaded = True

    def async_items(self):
        return list(self._items)

    async def async_create_item(self, data):
        item_id = len(self._items) + 1
        item = {CONF_ID: item_id, **data}
        self._items.append(item)
        self.created.append(item)
        return item

    async def async_delete_item(self, resource_id):
        self._items = [item for item in self._items if item[CONF_ID] != resource_id]
        self.deleted.append(resource_id)


class FakeYAMLResources(ResourceYAMLCollection):
    """YAML-backed fake resources used in tests."""

    def __init__(self, items: list[dict] | None = None) -> None:
        super().__init__(items or [])
        self.deleted: list[int] = []


def test_get_card_resource_definitions():
    """Test case for test_get_card_resource_definitions."""
    resources = scrypted._get_card_resource_definitions("tok")
    assert resources[0][1].endswith(".js")
    assert resources[1][1].endswith(".css")


async def test_register_no_lovelace_data_is_noop(hass):
    """Test case for test_register_no_lovelace_data_is_noop."""
    await scrypted._async_register_lovelace_resource(hass, "tok", "entry")
    assert scrypted._RESOURCE_TRACKER not in hass.data


async def test_register_storage_creates_resources(hass):
    """Test case for test_register_storage_creates_resources."""
    resources = FakeStorageResources()
    hass.data[LL_DOMAIN] = SimpleNamespace(resources=resources)
    await scrypted._async_register_lovelace_resource(hass, "tok", "entry")
    tracker = hass.data[scrypted._RESOURCE_TRACKER]
    assert set(tracker["entry"]) == {
        "/api/scrypted/tok/endpoint/@scrypted/nvr/assets/web-components.js",
        "/api/scrypted/tok/endpoint/@scrypted/nvr/assets/web-components.css",
    }
    assert resources.loaded
    assert len(resources.created) == 2


async def test_register_storage_skips_existing(hass):
    """Test case for test_register_storage_skips_existing."""
    base = "/api/scrypted/token/endpoint/@scrypted/nvr/assets/web-components"
    resources = FakeStorageResources(
        [
            {CONF_ID: 1, CONF_URL: f"{base}.js", "type": "module"},
            {CONF_ID: 2, CONF_URL: f"{base}.css", "type": "css"},
        ]
    )
    hass.data[LL_DOMAIN] = SimpleNamespace(resources=resources)
    await scrypted._async_register_lovelace_resource(hass, "token", "entry")
    assert scrypted._RESOURCE_TRACKER not in hass.data
    assert not resources.created


async def test_register_yaml_warns(hass, caplog):
    """Test case for test_register_yaml_warns."""
    hass.data[LL_DOMAIN] = SimpleNamespace(resources=FakeYAMLResources())
    await scrypted._async_register_lovelace_resource(hass, "tok", "entry")
    assert scrypted._RESOURCE_TRACKER not in hass.data
    assert "can't automatically be registered" in caplog.text


async def test_unregister_storage_removes_resources(hass):
    """Test case for test_unregister_storage_removes_resources."""
    base = "/api/scrypted/tok/endpoint/@scrypted/nvr/assets/web-components"
    resources = FakeStorageResources(
        [
            {CONF_ID: 10, CONF_URL: f"{base}.js"},
            {CONF_ID: 11, CONF_URL: f"{base}.css"},
        ]
    )
    hass.data[LL_DOMAIN] = SimpleNamespace(resources=resources)
    hass.data[scrypted._RESOURCE_TRACKER] = {"entry": {f"{base}.js", f"{base}.css"}}
    await scrypted._async_unregister_lovelace_resource(hass, "entry")
    assert set(resources.deleted) == {10, 11}
    assert scrypted._RESOURCE_TRACKER not in hass.data


async def test_unregister_empty_tracked_urls_cleans_tracker(hass):
    """Test case for test_unregister_empty_tracked_urls_cleans_tracker."""
    hass.data[scrypted._RESOURCE_TRACKER] = {"entry": set()}
    await scrypted._async_unregister_lovelace_resource(hass, "entry")
    assert scrypted._RESOURCE_TRACKER not in hass.data


async def test_unregister_without_lovelace_data_cleans_tracker(hass):
    """Test case for test_unregister_without_lovelace_data_cleans_tracker."""
    hass.data[scrypted._RESOURCE_TRACKER] = {"entry": {"/missing"}}
    await scrypted._async_unregister_lovelace_resource(hass, "entry")
    assert scrypted._RESOURCE_TRACKER not in hass.data


async def test_unregister_without_tracker_is_noop(hass):
    """Test case for test_unregister_without_tracker_is_noop."""
    await scrypted._async_unregister_lovelace_resource(hass, "entry")
    assert scrypted._RESOURCE_TRACKER not in hass.data


async def test_unregister_logs_missing_resources(hass, caplog):
    """Test case for test_unregister_logs_missing_resources."""
    base = "/api/scrypted/tok/endpoint/@scrypted/nvr/assets/web-components"
    resources = FakeStorageResources([{CONF_ID: 10, CONF_URL: f"{base}.js"}])
    hass.data[LL_DOMAIN] = SimpleNamespace(resources=resources)
    hass.data[scrypted._RESOURCE_TRACKER] = {"entry": {f"{base}.js", f"{base}.css"}}
    await scrypted._async_unregister_lovelace_resource(hass, "entry")
    assert resources.deleted == [10]
    assert "was not found" in caplog.text


async def test_unregister_yaml_resources_skip_deletion(hass):
    """Test case for test_unregister_yaml_resources_skip_deletion."""
    base = "/api/scrypted/tok/endpoint/@scrypted/nvr/assets/web-components"
    resources = FakeYAMLResources(
        [
            {CONF_ID: 10, CONF_URL: f"{base}.js"},
            {CONF_ID: 11, CONF_URL: f"{base}.css"},
        ]
    )
    hass.data[LL_DOMAIN] = SimpleNamespace(resources=resources)
    hass.data[scrypted._RESOURCE_TRACKER] = {"entry": {f"{base}.js", f"{base}.css"}}
    await scrypted._async_unregister_lovelace_resource(hass, "entry")
    assert not resources.deleted


async def test_async_setup_without_domain_config(hass, mock_scrypted_view):
    """Test case for test_async_setup_without_domain_config."""
    registered = {}
    hass.http = SimpleNamespace(
        register_view=lambda view: registered.setdefault("view", view)
    )
    result = await scrypted.async_setup(hass, {})
    assert result is True
    assert registered["view"] == "view"


async def test_async_setup_imports_yaml_config(
    hass, mock_scrypted_view, mock_async_create_notification, mock_flow_async_init
):
    """Test case for test_async_setup_imports_yaml_config."""
    hass.http = SimpleNamespace(register_view=lambda view: None)
    result = await scrypted.async_setup(hass, {DOMAIN: {"host": EXAMPLE_HOST}})
    await hass.async_block_till_done()
    assert result is False
    mock_flow_async_init.assert_awaited()
    assert (
        "Your Scrypted configuration"
        in mock_async_create_notification.notifications["created"][0][1]
    )


async def test_async_setup_entry_registers_resources_and_panel(
    hass,
    mock_register_lovelace_resource,
    mock_register_built_in_panel,
    mock_forward_entry_setups,
    mock_async_reload,
):
    """Test case for test_async_setup_entry_registers_resources_and_panel."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: EXAMPLE_HOST,
            CONF_ICON: "mdi:test",
            CONF_NAME: "Scrypted",
            CONF_USERNAME: "user",
        },
        options={
            CONF_AUTO_REGISTER_RESOURCES: True,
            CONF_SCRYPTED_NVR: False,
            CONF_ENABLE_ENTITIES: False,
            "device_types": ["Camera", "Doorbell"],
        },
    )
    entry.add_to_hass(hass)
    result = await scrypted.async_setup_entry(hass, entry)
    await hass.async_block_till_done()
    assert result is True
    mock_register_lovelace_resource.assert_awaited()
    mock_forward_entry_setups.assert_awaited()
    assert hass.data[DOMAIN]["token"] == entry
    assert entry.options[CONF_SCRYPTED_NVR] is False
    assert CONF_SCRYPTED_NVR not in entry.data
    assert not mock_async_reload.called


async def test_async_setup_entry_moves_auto_register_flag(
    hass,
    mock_register_lovelace_resource,
    mock_register_built_in_panel,
    mock_forward_entry_setups,
    mock_async_reload,
):
    """Test case for test_async_setup_entry_moves_auto_register_flag."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: EXAMPLE_HOST,
            CONF_ICON: "mdi:test",
            CONF_NAME: "Scrypted",
            CONF_USERNAME: "user",
            CONF_AUTO_REGISTER_RESOURCES: True,
            CONF_SCRYPTED_NVR: True,
        },
    )
    entry.add_to_hass(hass)
    result = await scrypted.async_setup_entry(hass, entry)
    assert result is False
    mock_async_reload.assert_called_once_with(entry.entry_id)
    assert CONF_AUTO_REGISTER_RESOURCES not in entry.data
    assert CONF_SCRYPTED_NVR not in entry.data
    assert entry.options[CONF_AUTO_REGISTER_RESOURCES] is True
    assert entry.options[CONF_SCRYPTED_NVR] is True


async def test_async_setup_entry_without_data_triggers_reauth(
    hass, mock_flow_async_init
):
    """Test case for test_async_setup_entry_without_data_triggers_reauth."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    result = await scrypted.async_setup_entry(hass, entry)
    await hass.async_block_till_done()
    assert result is False
    assert mock_flow_async_init.await_count == 1
    assert mock_flow_async_init.call_args.kwargs["context"]["source"] == SOURCE_REAUTH
    assert (
        mock_flow_async_init.call_args.kwargs["context"]["entry_id"] == entry.entry_id
    )


async def test_update_listener_moves_option_keys(hass, mock_async_reload):
    """Test case for test_update_listener_moves_option_keys."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: EXAMPLE_HOST,
            CONF_ICON: "mdi:test",
            CONF_NAME: "Scrypted",
            CONF_USERNAME: "user",
            CONF_AUTO_REGISTER_RESOURCES: True,
            CONF_SCRYPTED_NVR: True,
        },
        options={},
    )
    entry.add_to_hass(hass)
    await scrypted._async_update_listener(hass, entry)
    assert CONF_AUTO_REGISTER_RESOURCES not in entry.data
    assert CONF_SCRYPTED_NVR not in entry.data
    assert entry.options[CONF_AUTO_REGISTER_RESOURCES] is True
    assert entry.options[CONF_SCRYPTED_NVR] is True
    mock_async_reload.assert_called_once_with(entry.entry_id)


async def test_ensure_entry_options_no_changes(hass, mock_async_update_entry):
    """Test case for test_ensure_entry_options_no_changes."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: EXAMPLE_HOST,
            CONF_ICON: "mdi:test",
            CONF_NAME: "Scrypted",
            CONF_USERNAME: "user",
        },
        options={
            CONF_AUTO_REGISTER_RESOURCES: False,
            CONF_SCRYPTED_NVR: False,
            CONF_ENABLE_ENTITIES: False,
            "device_types": ["Camera", "Doorbell"],
        },
    )
    entry.add_to_hass(hass)
    changed = await scrypted._async_ensure_entry_options(hass, entry)
    assert changed is False
    mock_async_update_entry.assert_not_called()


async def test_ensure_entry_options_adds_defaults(hass, mock_async_update_entry):
    """Test case for test_ensure_entry_options_adds_defaults."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: EXAMPLE_HOST,
            CONF_ICON: "mdi:test",
            CONF_NAME: "Scrypted",
            CONF_USERNAME: "user",
        },
        options={},
    )
    entry.add_to_hass(hass)
    changed = await scrypted._async_ensure_entry_options(hass, entry)
    assert changed is True
    mock_async_update_entry.assert_called_once()


async def test_async_setup_entry_handles_missing_token(
    hass, mock_flow_async_init, mock_retrieve_token_none
):
    """Test case for test_async_setup_entry_handles_missing_token."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: EXAMPLE_HOST,
            CONF_ICON: "mdi:test",
            CONF_NAME: "Scrypted",
            CONF_USERNAME: "user",
        },
        options={
            CONF_AUTO_REGISTER_RESOURCES: False,
            CONF_SCRYPTED_NVR: False,
            CONF_ENABLE_ENTITIES: False,
            "device_types": ["Camera", "Doorbell"],
        },
    )
    entry.add_to_hass(hass)
    result = await scrypted.async_setup_entry(hass, entry)
    await hass.async_block_till_done()
    assert result is False
    assert mock_flow_async_init.call_args.kwargs["context"]["source"] == SOURCE_REAUTH


@pytest.mark.parametrize("status", [401, 403])
async def test_async_setup_entry_auth_error_triggers_reauth(
    hass, mock_flow_async_init, patch_retrieve_token, status
):
    """Test case for test_async_setup_entry_auth_error_triggers_reauth."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: EXAMPLE_HOST,
            CONF_ICON: "mdi:test",
            CONF_NAME: "Scrypted",
            CONF_USERNAME: "user",
        },
        options={
            CONF_AUTO_REGISTER_RESOURCES: False,
            CONF_SCRYPTED_NVR: False,
            CONF_ENABLE_ENTITIES: False,
            "device_types": ["Camera", "Doorbell"],
        },
    )
    entry.add_to_hass(hass)

    async def _raise(*args, **kwargs):
        raise ClientResponseError(MagicMock(), (), status=status)

    with patch_retrieve_token(_raise):
        result = await scrypted.async_setup_entry(hass, entry)
    await hass.async_block_till_done()
    assert result is False
    assert mock_flow_async_init.call_args.kwargs["context"]["source"] == SOURCE_REAUTH


async def test_async_setup_entry_client_connector_error(
    hass, mock_retrieve_token_client_error
):
    """Test case for test_async_setup_entry_client_connector_error."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: EXAMPLE_HOST,
            CONF_ICON: "mdi:test",
            CONF_NAME: "Scrypted",
            CONF_USERNAME: "user",
        },
        options={
            CONF_AUTO_REGISTER_RESOURCES: False,
            CONF_SCRYPTED_NVR: False,
            CONF_ENABLE_ENTITIES: False,
            "device_types": ["Camera", "Doorbell"],
        },
    )
    entry.add_to_hass(hass)
    with pytest.raises(ConfigEntryNotReady):
        await scrypted.async_setup_entry(hass, entry)


async def test_async_setup_entry_other_exception_propagates(
    hass, mock_retrieve_token_runtime_error
):
    """Test case for test_async_setup_entry_other_exception_propagates."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: EXAMPLE_HOST,
            CONF_ICON: "mdi:test",
            CONF_NAME: "Scrypted",
            CONF_USERNAME: "user",
        },
        options={
            CONF_AUTO_REGISTER_RESOURCES: False,
            CONF_SCRYPTED_NVR: False,
            CONF_ENABLE_ENTITIES: False,
            "device_types": ["Camera", "Doorbell"],
        },
    )
    entry.add_to_hass(hass)
    with pytest.raises(RuntimeError):
        await scrypted.async_setup_entry(hass, entry)


async def test_async_unload_entry(
    hass, mock_unregister_lovelace_resource, mock_remove_panel
):
    """Test case for test_async_unload_entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: EXAMPLE_HOST,
            CONF_ICON: "mdi:test",
            CONF_NAME: "Scrypted",
            CONF_USERNAME: "user",
        },
    )
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})["token"] = entry
    hass.data.setdefault(scrypted._RESOURCE_TRACKER, {})[entry.entry_id] = set()
    result = await scrypted.async_unload_entry(hass, entry)
    assert result is True
    mock_unregister_lovelace_resource.assert_awaited()
    assert f"{DOMAIN}_token" in mock_remove_panel.removed_panels
    assert DOMAIN not in hass.data


async def test_panel_registered_with_token(
    hass, mock_register_built_in_panel, mock_forward_entry_setups
):
    """Test that panel is registered using token in the URL path."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: EXAMPLE_HOST,
            CONF_ICON: "mdi:test",
            CONF_NAME: "Scrypted",
            CONF_USERNAME: "user",
        },
        options={
            CONF_AUTO_REGISTER_RESOURCES: False,
            CONF_SCRYPTED_NVR: False,
            CONF_ENABLE_ENTITIES: False,
            "device_types": ["Camera", "Doorbell"],
        },
    )
    entry.add_to_hass(hass)
    result = await scrypted.async_setup_entry(hass, entry)
    assert result is True
    assert (
        mock_register_built_in_panel.captured_kwargs["frontend_url_path"]
        == f"{DOMAIN}_token"
    )


async def test_panel_unregistered_with_token(
    hass, mock_unregister_lovelace_resource, mock_remove_panel
):
    """Test that panel is unregistered using the same token-based URL path."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: EXAMPLE_HOST,
            CONF_ICON: "mdi:test",
            CONF_NAME: "Scrypted",
            CONF_USERNAME: "user",
        },
    )
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})["token"] = entry
    result = await scrypted.async_unload_entry(hass, entry)
    assert result is True
    assert mock_remove_panel.removed_panels == [f"{DOMAIN}_token"]


async def test_panel_reload_uses_consistent_url_path(hass, mock_panel_lifecycle):
    """Test that panel can be reloaded without 'Overwriting panel' errors.

    This verifies that both registration and unregistration use the same
    token-based URL path, allowing clean reloads.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: EXAMPLE_HOST,
            CONF_ICON: "mdi:test",
            CONF_NAME: "Scrypted",
            CONF_USERNAME: "user",
        },
        options={
            CONF_AUTO_REGISTER_RESOURCES: False,
            CONF_SCRYPTED_NVR: False,
            CONF_ENABLE_ENTITIES: False,
            "device_types": ["Camera", "Doorbell"],
        },
    )
    entry.add_to_hass(hass)

    # First setup
    result = await scrypted.async_setup_entry(hass, entry)
    assert result is True
    assert f"{DOMAIN}_token" in mock_panel_lifecycle["registered"]

    # Unload
    result = await scrypted.async_unload_entry(hass, entry)
    assert result is True
    assert f"{DOMAIN}_token" not in mock_panel_lifecycle["registered"]

    # Re-add token mapping for second setup
    hass.data.setdefault(DOMAIN, {})

    # Second setup (simulating reload) - should not raise ValueError
    result = await scrypted.async_setup_entry(hass, entry)
    assert result is True
    assert f"{DOMAIN}_token" in mock_panel_lifecycle["registered"]


async def test_setup_entry_creates_client_and_unloads(hass, enable_custom_integrations):
    """Entities enabled: client connects on setup and disconnects on unload."""
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
            "device_types": ["Camera", "Doorbell"],
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    client = entry.runtime_data.client
    assert client is not None
    assert client.connected

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert client.connected is False


async def test_setup_entry_entities_disabled(hass, enable_custom_integrations):
    """Entities disabled: no client, panel-only setup still succeeds."""
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
            CONF_ENABLE_ENTITIES: False,
            "device_types": ["Camera", "Doorbell"],
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.client is None


async def test_setup_entry_auth_error_starts_reauth(hass):
    """HTTP 401 from token retrieval starts the reauth flow."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "example", CONF_USERNAME: "u"},
        options={
            CONF_AUTO_REGISTER_RESOURCES: False,
            CONF_SCRYPTED_NVR: False,
            CONF_ENABLE_ENTITIES: False,
            "device_types": ["Camera", "Doorbell"],
        },
    )
    entry.add_to_hass(hass)

    async def _raise(data, session):
        raise ClientResponseError(request_info=MagicMock(), history=(), status=401)

    flow_init = AsyncMock()
    with (
        patch.object(scrypted, "retrieve_token", _raise),
        patch.object(hass.config_entries.flow, "async_init", flow_init),
    ):
        result = await scrypted.async_setup_entry(hass, entry)
        await hass.async_block_till_done()
        assert result is False
        flow_init.assert_awaited()


async def test_setup_entry_not_ready_on_engineio_failure(
    hass, enable_custom_integrations
):
    """engine.io connect failure raises ConfigEntryNotReady (setup retry)."""

    async def _fail(self):
        raise ScryptedConnectionError("nope")

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "1.2.3.4",
            CONF_USERNAME: "u",
            CONF_NAME: "Scrypted",
            CONF_ICON: "mdi:memory",
        },
        options={
            CONF_AUTO_REGISTER_RESOURCES: False,
            CONF_SCRYPTED_NVR: False,
            CONF_ENABLE_ENTITIES: True,
            "device_types": ["Camera", "Doorbell"],
        },
    )
    entry.add_to_hass(hass)
    with patch.object(scrypted.ScryptedClient, "async_connect", _fail):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_unload_entry_fails_when_platforms_fail(hass):
    """Unload aborts when platform unload fails."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "example"})
    entry.add_to_hass(hass)
    with patch.object(
        hass.config_entries,
        "async_unload_platforms",
        AsyncMock(return_value=False),
    ):
        assert await scrypted.async_unload_entry(hass, entry) is False


async def test_remove_config_entry_device(hass, fake_sdk, enable_custom_integrations):
    """Devices are only removable once scrypted stops exposing them."""
    entry = await setup_entry(hass)
    device_registry = dr.async_get(hass)
    hub = device_registry.async_get_device_by_identifier(
        (DOMAIN, entry.entry_id), entry.entry_id
    )
    cam = device_registry.async_get_device_by_identifier(
        (DOMAIN, f"{entry.entry_id}_cam1"), entry.entry_id
    )
    bell = device_registry.async_get_device_by_identifier(
        (DOMAIN, f"{entry.entry_id}_bell1"), entry.entry_id
    )
    assert hub and cam and bell

    # hub and still-exposed devices are not removable
    assert not await scrypted.async_remove_config_entry_device(hass, entry, hub)
    assert not await scrypted.async_remove_config_entry_device(hass, entry, cam)

    # device gone from scrypted -> removable
    fake_sdk.systemManager.systemState.pop("cam1")
    assert await scrypted.async_remove_config_entry_device(hass, entry, cam)

    # device still in scrypted but type no longer in the allowlist -> removable
    fake_sdk.systemManager.systemState["bell1"]["type"]["value"] = "Vacuum"
    assert await scrypted.async_remove_config_entry_device(hass, entry, bell)


async def test_remove_config_entry_device_entities_disabled(
    hass, fake_sdk, enable_custom_integrations
):
    """With entities disabled, any leftover device is removable."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "x"})
    entry.add_to_hass(hass)
    entry.runtime_data = SimpleNamespace(client=None)
    device_entry = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={
            ("other_domain", "irrelevant"),
            (DOMAIN, "other_entry_device"),
            (DOMAIN, f"{entry.entry_id}_ghost"),
        },
    )
    assert await scrypted.async_remove_config_entry_device(hass, entry, device_entry)


async def test_failed_connect_does_not_publish_token(hass, mock_forward_entry_setups):
    """A setup that cannot connect leaves no token mapping behind."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: EXAMPLE_HOST,
            CONF_ICON: "mdi:test",
            CONF_NAME: "Scrypted",
            CONF_USERNAME: "user",
        },
        options={
            CONF_AUTO_REGISTER_RESOURCES: False,
            CONF_SCRYPTED_NVR: False,
            CONF_ENABLE_ENTITIES: True,
            "device_types": ["Camera", "Doorbell"],
        },
    )
    entry.add_to_hass(hass)

    with (
        patch.object(
            scrypted.ScryptedClient,
            "async_connect",
            AsyncMock(side_effect=ScryptedConnectionError("nope")),
        ),
        pytest.raises(ConfigEntryNotReady),
    ):
        await scrypted.async_setup_entry(hass, entry)

    # The proxy view resolves entries through hass.data; a token left there
    # would keep serving an entry that never loaded.
    assert not hass.data.get(DOMAIN)


async def test_panel_opts_out_of_automatic_safe_area_padding(
    hass, mock_register_built_in_panel, mock_forward_entry_setups
):
    """The panel handles safe-area insets itself, so HA must not also pad it."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: EXAMPLE_HOST,
            CONF_ICON: "mdi:test",
            CONF_NAME: "Scrypted",
            CONF_USERNAME: "user",
        },
        options={
            CONF_AUTO_REGISTER_RESOURCES: False,
            CONF_SCRYPTED_NVR: False,
            CONF_ENABLE_ENTITIES: False,
            "device_types": ["Camera", "Doorbell"],
        },
    )
    entry.add_to_hass(hass)

    assert await scrypted.async_setup_entry(hass, entry)

    # entrypoint.js sizes :host against the viewport and subtracts the insets
    # itself. If HA also padded the container the two boxes would disagree and
    # the bottom of the iframe would land off-screen on a device with a home
    # indicator.
    panel_custom = mock_register_built_in_panel.captured_kwargs["config"][
        "_panel_custom"
    ]
    assert panel_custom["handle_safe_area"] is True
