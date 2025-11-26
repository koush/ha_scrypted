"""Tests for the Scrypted integration setup logic."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import ClientConnectorError
from homeassistant.components.lovelace.const import DOMAIN as LL_DOMAIN
from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant.const import (
    CONF_HOST,
    CONF_ICON,
    CONF_ID,
    CONF_NAME,
    CONF_URL,
    CONF_USERNAME,
)
from homeassistant.exceptions import ConfigEntryNotReady

import custom_components.scrypted as scrypted
from custom_components.scrypted.const import (
    CONF_AUTO_REGISTER_RESOURCES,
    CONF_SCRYPTED_NVR,
    DOMAIN,
)

from pytest_homeassistant_custom_component.common import MockConfigEntry


class _BaseResources:
    """Base resource collection used for storage + YAML tests."""

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


class FakeStorageResources(_BaseResources):
    """Storage-backed fake resources used in tests."""


class FakeYAMLResources(_BaseResources):
    """YAML-backed fake resources used in tests."""


@pytest.fixture(autouse=True)
def patch_resource_classes(monkeypatch):
    """Patch Lovelace resource helpers to use fakes."""
    monkeypatch.setattr(scrypted, "ResourceStorageCollection", FakeStorageResources)
    monkeypatch.setattr(scrypted, "ResourceYAMLCollection", FakeYAMLResources)


def _attach_resources(hass, resources):
    """Attach fake Lovelace resources to hass data."""
    hass.data[LL_DOMAIN] = SimpleNamespace(resources=resources)


def test_get_card_resource_definitions():
    """Test case for test_get_card_resource_definitions."""
    resources = scrypted._get_card_resource_definitions("tok")
    assert resources[0][1].endswith(".js")
    assert resources[1][1].endswith(".css")


@pytest.mark.asyncio
async def test_register_no_lovelace_data_is_noop(hass):
    """Test case for test_register_no_lovelace_data_is_noop."""
    await scrypted._async_register_lovelace_resource(hass, "tok", "entry")
    assert scrypted._RESOURCE_TRACKER not in hass.data


@pytest.mark.asyncio
async def test_register_storage_creates_resources(hass):
    """Test case for test_register_storage_creates_resources."""
    resources = FakeStorageResources()
    _attach_resources(hass, resources)
    await scrypted._async_register_lovelace_resource(hass, "tok", "entry")
    tracker = hass.data[scrypted._RESOURCE_TRACKER]
    assert set(tracker["entry"]) == {
        "/api/scrypted/tok/endpoint/@scrypted/nvr/assets/web-components.js",
        "/api/scrypted/tok/endpoint/@scrypted/nvr/assets/web-components.css",
    }
    assert resources.loaded
    assert len(resources.created) == 2


@pytest.mark.asyncio
async def test_register_storage_skips_existing(hass):
    """Test case for test_register_storage_skips_existing."""
    base = "/api/scrypted/token/endpoint/@scrypted/nvr/assets/web-components"
    resources = FakeStorageResources(
        [
            {CONF_ID: 1, CONF_URL: f"{base}.js", "type": "module"},
            {CONF_ID: 2, CONF_URL: f"{base}.css", "type": "css"},
        ]
    )
    _attach_resources(hass, resources)
    await scrypted._async_register_lovelace_resource(hass, "token", "entry")
    assert scrypted._RESOURCE_TRACKER not in hass.data
    assert not resources.created


@pytest.mark.asyncio
async def test_register_yaml_warns(hass, caplog):
    """Test case for test_register_yaml_warns."""
    _attach_resources(hass, FakeYAMLResources())
    await scrypted._async_register_lovelace_resource(hass, "tok", "entry")
    assert scrypted._RESOURCE_TRACKER not in hass.data
    assert "can't automatically be registered" in caplog.text


@pytest.mark.asyncio
async def test_unregister_storage_removes_resources(hass):
    """Test case for test_unregister_storage_removes_resources."""
    base = "/api/scrypted/tok/endpoint/@scrypted/nvr/assets/web-components"
    resources = FakeStorageResources(
        [
            {CONF_ID: 10, CONF_URL: f"{base}.js"},
            {CONF_ID: 11, CONF_URL: f"{base}.css"},
        ]
    )
    _attach_resources(hass, resources)
    hass.data[scrypted._RESOURCE_TRACKER] = {
        "entry": {f"{base}.js", f"{base}.css"}
    }
    await scrypted._async_unregister_lovelace_resource(hass, "tok", "entry")
    assert set(resources.deleted) == {10, 11}
    assert scrypted._RESOURCE_TRACKER not in hass.data


@pytest.mark.asyncio
async def test_unregister_empty_tracked_urls_cleans_tracker(hass):
    """Test case for test_unregister_empty_tracked_urls_cleans_tracker."""
    hass.data[scrypted._RESOURCE_TRACKER] = {"entry": set()}
    await scrypted._async_unregister_lovelace_resource(hass, "tok", "entry")
    assert scrypted._RESOURCE_TRACKER not in hass.data


@pytest.mark.asyncio
async def test_unregister_without_lovelace_data_cleans_tracker(hass):
    """Test case for test_unregister_without_lovelace_data_cleans_tracker."""
    hass.data[scrypted._RESOURCE_TRACKER] = {"entry": {"/missing"}}
    await scrypted._async_unregister_lovelace_resource(hass, "tok", "entry")
    assert scrypted._RESOURCE_TRACKER not in hass.data


@pytest.mark.asyncio
async def test_unregister_without_tracker_is_noop(hass):
    """Test case for test_unregister_without_tracker_is_noop."""
    await scrypted._async_unregister_lovelace_resource(hass, "tok", "entry")
    assert scrypted._RESOURCE_TRACKER not in hass.data


@pytest.mark.asyncio
async def test_unregister_logs_missing_resources(hass, caplog):
    """Test case for test_unregister_logs_missing_resources."""
    base = "/api/scrypted/tok/endpoint/@scrypted/nvr/assets/web-components"
    resources = FakeStorageResources([{CONF_ID: 10, CONF_URL: f"{base}.js"}])
    _attach_resources(hass, resources)
    hass.data[scrypted._RESOURCE_TRACKER] = {
        "entry": {f"{base}.js", f"{base}.css"}
    }
    await scrypted._async_unregister_lovelace_resource(hass, "tok", "entry")
    assert resources.deleted == [10]
    assert "was not found" in caplog.text


@pytest.mark.asyncio
async def test_unregister_yaml_resources_skip_deletion(hass):
    """Test case for test_unregister_yaml_resources_skip_deletion."""
    base = "/api/scrypted/tok/endpoint/@scrypted/nvr/assets/web-components"
    resources = FakeYAMLResources(
        [
            {CONF_ID: 10, CONF_URL: f"{base}.js"},
            {CONF_ID: 11, CONF_URL: f"{base}.css"},
        ]
    )
    _attach_resources(hass, resources)
    hass.data[scrypted._RESOURCE_TRACKER] = {
        "entry": {f"{base}.js", f"{base}.css"}
    }
    await scrypted._async_unregister_lovelace_resource(hass, "tok", "entry")
    assert not resources.deleted


@pytest.mark.asyncio
async def test_async_setup_without_domain_config(hass, monkeypatch):
    """Test case for test_async_setup_without_domain_config."""
    registered = {}
    hass.http = SimpleNamespace(register_view=lambda view: registered.setdefault("view", view))
    monkeypatch.setattr(scrypted, "ScryptedView", lambda hass, session: "view")
    result = await scrypted.async_setup(hass, {})
    assert result is True
    assert registered["view"] == "view"


@pytest.mark.asyncio
async def test_async_setup_imports_yaml_config(hass, monkeypatch):
    """Test case for test_async_setup_imports_yaml_config."""
    hass.http = SimpleNamespace(register_view=lambda view: None)
    monkeypatch.setattr(scrypted, "ScryptedView", lambda hass, session: None)
    notifications = {}
    monkeypatch.setattr(
        scrypted,
        "async_create",
        lambda *args, **kwargs: notifications.setdefault("created", (args, kwargs)),
    )
    flow_init = AsyncMock(return_value={"type": "form"})
    monkeypatch.setattr(hass.config_entries.flow, "async_init", flow_init)
    result = await scrypted.async_setup(hass, {DOMAIN: {"host": "example"}})
    await hass.async_block_till_done()
    assert result is False
    flow_init.assert_awaited()
    assert "Your Scrypted configuration" in notifications["created"][0][1]


@pytest.mark.asyncio
async def test_async_setup_entry_registers_resources_and_panel(hass, monkeypatch):
    """Test case for test_async_setup_entry_registers_resources_and_panel."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "example",
            CONF_ICON: "mdi:test",
            CONF_NAME: "Scrypted",
            CONF_USERNAME: "user",
        },
        options={
            CONF_AUTO_REGISTER_RESOURCES: True,
            CONF_SCRYPTED_NVR: False,
        },
    )
    entry.add_to_hass(hass)
    register_resource = AsyncMock()
    forward_setups = AsyncMock()
    reload_mock = AsyncMock()
    monkeypatch.setattr(scrypted, "_async_register_lovelace_resource", register_resource)
    monkeypatch.setattr(scrypted, "async_register_built_in_panel", lambda *args, **kwargs: kwargs)
    monkeypatch.setattr(hass.config_entries, "async_forward_entry_setups", forward_setups)
    monkeypatch.setattr(hass.config_entries, "async_reload", reload_mock)
    result = await scrypted.async_setup_entry(hass, entry)
    await hass.async_block_till_done()
    assert result is True
    register_resource.assert_awaited()
    forward_setups.assert_awaited()
    assert hass.data[DOMAIN]["token"] == entry
    assert entry.options[CONF_SCRYPTED_NVR] is False
    assert CONF_SCRYPTED_NVR not in entry.data
    assert not reload_mock.called


@pytest.mark.asyncio
async def test_async_setup_entry_moves_auto_register_flag(hass, monkeypatch):
    """Test case for test_async_setup_entry_moves_auto_register_flag."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "example",
            CONF_ICON: "mdi:test",
            CONF_NAME: "Scrypted",
            CONF_USERNAME: "user",
            CONF_AUTO_REGISTER_RESOURCES: True,
            CONF_SCRYPTED_NVR: True,
        },
    )
    entry.add_to_hass(hass)
    register_resource = AsyncMock()
    reload_mock = AsyncMock()
    monkeypatch.setattr(scrypted, "_async_register_lovelace_resource", register_resource)
    monkeypatch.setattr(scrypted, "async_register_built_in_panel", lambda *args, **kwargs: None)
    monkeypatch.setattr(hass.config_entries, "async_forward_entry_setups", AsyncMock())
    monkeypatch.setattr(hass.config_entries, "async_reload", reload_mock)
    result = await scrypted.async_setup_entry(hass, entry)
    assert result is False
    reload_mock.assert_called_once_with(entry.entry_id)
    assert CONF_AUTO_REGISTER_RESOURCES not in entry.data
    assert CONF_SCRYPTED_NVR not in entry.data
    assert entry.options[CONF_AUTO_REGISTER_RESOURCES] is True
    assert entry.options[CONF_SCRYPTED_NVR] is True


@pytest.mark.asyncio
async def test_async_setup_entry_without_data_triggers_reauth(hass, monkeypatch):
    """Test case for test_async_setup_entry_without_data_triggers_reauth."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    flow_init = AsyncMock(return_value={"type": "form"})
    monkeypatch.setattr(hass.config_entries.flow, "async_init", flow_init)
    result = await scrypted.async_setup_entry(hass, entry)
    await hass.async_block_till_done()
    assert result is False
    assert flow_init.await_count == 1
    assert flow_init.call_args.kwargs["context"]["source"] == SOURCE_REAUTH
    assert flow_init.call_args.kwargs["context"]["entry_id"] == entry.entry_id


@pytest.mark.asyncio
async def test_update_listener_moves_option_keys(hass, monkeypatch):
    """Test case for test_update_listener_moves_option_keys."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "example",
            CONF_ICON: "mdi:test",
            CONF_NAME: "Scrypted",
            CONF_USERNAME: "user",
            CONF_AUTO_REGISTER_RESOURCES: True,
            CONF_SCRYPTED_NVR: True,
        },
        options={},
    )
    entry.add_to_hass(hass)
    reload_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(hass.config_entries, "async_reload", reload_mock)
    await scrypted._async_update_listener(hass, entry)
    assert CONF_AUTO_REGISTER_RESOURCES not in entry.data
    assert CONF_SCRYPTED_NVR not in entry.data
    assert entry.options[CONF_AUTO_REGISTER_RESOURCES] is True
    assert entry.options[CONF_SCRYPTED_NVR] is True
    reload_mock.assert_called_once_with(entry.entry_id)


@pytest.mark.asyncio
async def test_ensure_entry_options_no_changes(hass, monkeypatch):
    """Test case for test_ensure_entry_options_no_changes."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "example",
            CONF_ICON: "mdi:test",
            CONF_NAME: "Scrypted",
            CONF_USERNAME: "user",
        },
        options={
            CONF_AUTO_REGISTER_RESOURCES: False,
            CONF_SCRYPTED_NVR: False,
        },
    )
    entry.add_to_hass(hass)
    update_mock = MagicMock()
    monkeypatch.setattr(hass.config_entries, "async_update_entry", update_mock)
    changed = await scrypted._async_ensure_entry_options(hass, entry)
    assert changed is False
    update_mock.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_entry_options_adds_defaults(hass, monkeypatch):
    """Test case for test_ensure_entry_options_adds_defaults."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "example",
            CONF_ICON: "mdi:test",
            CONF_NAME: "Scrypted",
            CONF_USERNAME: "user",
        },
        options={},
    )
    entry.add_to_hass(hass)
    update_mock = MagicMock()
    monkeypatch.setattr(hass.config_entries, "async_update_entry", update_mock)
    changed = await scrypted._async_ensure_entry_options(hass, entry)
    assert changed is True
    update_mock.assert_called_once()


@pytest.mark.asyncio
async def test_async_setup_entry_handles_missing_token(hass, monkeypatch):
    """Test case for test_async_setup_entry_handles_missing_token."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "example",
            CONF_ICON: "mdi:test",
            CONF_NAME: "Scrypted",
            CONF_USERNAME: "user",
        },
        options={
            CONF_AUTO_REGISTER_RESOURCES: False,
            CONF_SCRYPTED_NVR: False,
        },
    )
    entry.add_to_hass(hass)
    flow_init = AsyncMock(return_value={"type": "form"})
    monkeypatch.setattr(hass.config_entries.flow, "async_init", flow_init)

    async def _no_token(*args, **kwargs):
        return None

    monkeypatch.setattr(scrypted, "retrieve_token", _no_token)
    result = await scrypted.async_setup_entry(hass, entry)
    await hass.async_block_till_done()
    assert result is False
    assert flow_init.call_args.kwargs["context"]["source"] == SOURCE_REAUTH


@pytest.mark.asyncio
async def test_async_setup_entry_client_connector_error(hass, monkeypatch):
    """Test case for test_async_setup_entry_client_connector_error."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "example",
            CONF_ICON: "mdi:test",
            CONF_NAME: "Scrypted",
            CONF_USERNAME: "user",
        },
        options={
            CONF_AUTO_REGISTER_RESOURCES: False,
            CONF_SCRYPTED_NVR: False,
        },
    )
    entry.add_to_hass(hass)

    async def _raise(*args, **kwargs):
        raise ClientConnectorError(SimpleNamespace(), OSError())

    monkeypatch.setattr(scrypted, "retrieve_token", _raise)
    with pytest.raises(ConfigEntryNotReady):
        await scrypted.async_setup_entry(hass, entry)


@pytest.mark.asyncio
async def test_async_setup_entry_other_exception_propagates(hass, monkeypatch):
    """Test case for test_async_setup_entry_other_exception_propagates."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "example",
            CONF_ICON: "mdi:test",
            CONF_NAME: "Scrypted",
            CONF_USERNAME: "user",
        },
        options={
            CONF_AUTO_REGISTER_RESOURCES: False,
            CONF_SCRYPTED_NVR: False,
        },
    )
    entry.add_to_hass(hass)

    async def _raise(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(scrypted, "retrieve_token", _raise)
    with pytest.raises(RuntimeError):
        await scrypted.async_setup_entry(hass, entry)


@pytest.mark.asyncio
async def test_async_unload_entry(hass, monkeypatch):
    """Test case for test_async_unload_entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "example",
            CONF_ICON: "mdi:test",
            CONF_NAME: "Scrypted",
            CONF_USERNAME: "user",
        },
    )
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})["token"] = entry
    hass.data.setdefault(scrypted._RESOURCE_TRACKER, {})[entry.entry_id] = set()
    unregister = AsyncMock()
    monkeypatch.setattr(scrypted, "_async_unregister_lovelace_resource", unregister)
    removed = {}
    monkeypatch.setattr(scrypted, "async_remove_panel", lambda *args, **kwargs: removed.setdefault("called", True))
    result = await scrypted.async_unload_entry(hass, entry)
    assert result is True
    unregister.assert_awaited()
    assert removed["called"] is True
    assert DOMAIN not in hass.data
