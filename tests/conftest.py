"""Shared pytest fixtures for Scrypted tests."""

import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiohttp import ClientConnectorError
import pytest

from homeassistant import loader

pytest_plugins = ["pytest_homeassistant_custom_component"]

from custom_components import scrypted  # noqa: E402
from custom_components.scrypted import config_flow  # noqa: E402
from custom_components.scrypted.const import DOMAIN  # noqa: E402


@pytest.fixture(autouse=True)
def _register_scrypted_flow(hass):
    """Register the config flow module so HA can resolve it."""
    module = importlib.import_module("custom_components.scrypted.config_flow")
    hass.data[loader.DATA_COMPONENTS][f"{DOMAIN}.config_flow"] = module


@pytest.fixture(autouse=True)
def mock_async_get_clientsession():
    """Prevent tests from creating real aiohttp sessions."""
    fake_session = SimpleNamespace()
    with (
        patch.object(scrypted, "async_get_clientsession", return_value=fake_session),
        patch.object(config_flow, "async_get_clientsession", return_value=fake_session),
    ):
        yield fake_session


@pytest.fixture(autouse=True)
def mock_retrieve_token():
    """Return a canned token unless a test overrides the patch."""

    async def _fake_retrieve(data, session):
        return "token"

    with (
        patch.object(
            scrypted, "retrieve_token", side_effect=_fake_retrieve
        ) as scrypted_mock,
        patch.object(
            config_flow, "retrieve_token", side_effect=_fake_retrieve
        ) as config_flow_mock,
    ):
        yield {"scrypted": scrypted_mock, "config_flow": config_flow_mock}


# ---------------------------------------------------------------------------
# Reusable patch fixtures for common mocks
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_retrieve_token_error():
    """Patch retrieve_token to raise ValueError (invalid credentials)."""

    async def _raise(*args, **kwargs):
        raise ValueError

    with (
        patch.object(scrypted, "retrieve_token", side_effect=_raise) as scrypted_mock,
        patch.object(
            config_flow, "retrieve_token", side_effect=_raise
        ) as config_flow_mock,
    ):
        yield {"scrypted": scrypted_mock, "config_flow": config_flow_mock}


@pytest.fixture
def mock_retrieve_token_none():
    """Patch retrieve_token to return None (missing token)."""

    async def _no_token(*args, **kwargs):
        return None

    with (
        patch.object(
            scrypted, "retrieve_token", side_effect=_no_token
        ) as scrypted_mock,
        patch.object(
            config_flow, "retrieve_token", side_effect=_no_token
        ) as config_flow_mock,
    ):
        yield {"scrypted": scrypted_mock, "config_flow": config_flow_mock}


@pytest.fixture
def mock_register_lovelace_resource():
    """Patch _async_register_lovelace_resource."""
    with patch.object(
        scrypted, "_async_register_lovelace_resource", new_callable=AsyncMock
    ) as mock:
        yield mock


@pytest.fixture
def mock_unregister_lovelace_resource():
    """Patch _async_unregister_lovelace_resource."""
    with patch.object(
        scrypted, "_async_unregister_lovelace_resource", new_callable=AsyncMock
    ) as mock:
        yield mock


@pytest.fixture
def mock_register_built_in_panel():
    """Patch async_register_built_in_panel and capture kwargs."""
    captured_kwargs = {}

    def _capture(*args, **kwargs):
        captured_kwargs.update(kwargs)

    with patch.object(
        scrypted, "async_register_built_in_panel", side_effect=_capture
    ) as mock:
        mock.captured_kwargs = captured_kwargs
        yield mock


@pytest.fixture
def mock_remove_panel():
    """Patch async_remove_panel and track removed panels."""
    removed_panels = []

    def _remove(hass, panel_name):
        removed_panels.append(panel_name)

    with patch.object(scrypted, "async_remove_panel", side_effect=_remove) as mock:
        mock.removed_panels = removed_panels
        yield mock


@pytest.fixture
def mock_forward_entry_setups(hass):
    """Patch hass.config_entries.async_forward_entry_setups."""
    with patch.object(
        hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock
    ) as mock:
        yield mock


@pytest.fixture
def mock_async_reload(hass):
    """Patch hass.config_entries.async_reload."""
    with patch.object(
        hass.config_entries, "async_reload", new_callable=AsyncMock
    ) as mock:
        yield mock


@pytest.fixture
def mock_flow_async_init(hass):
    """Patch hass.config_entries.flow.async_init."""
    with patch.object(
        hass.config_entries.flow, "async_init", new_callable=AsyncMock
    ) as mock:
        mock.return_value = {"type": "form"}
        yield mock


@pytest.fixture
def mock_async_update_entry(hass):
    """Patch hass.config_entries.async_update_entry."""
    with patch.object(hass.config_entries, "async_update_entry") as mock:
        yield mock


@pytest.fixture
def mock_async_create_notification():
    """Patch async_create for persistent notifications."""
    notifications = {}

    def _create(*args, **kwargs):
        notifications["created"] = (args, kwargs)

    with patch.object(scrypted, "async_create", side_effect=_create) as mock:
        mock.notifications = notifications
        yield mock


@pytest.fixture
def mock_scrypted_view():
    """Patch ScryptedView."""
    with patch.object(scrypted, "ScryptedView", return_value="view") as mock:
        yield mock


@pytest.fixture
def mock_retrieve_token_client_error():
    """Patch retrieve_token to raise ClientConnectorError."""

    async def _raise(*args, **kwargs):
        raise ClientConnectorError(SimpleNamespace(), OSError())

    with (
        patch.object(scrypted, "retrieve_token", side_effect=_raise) as scrypted_mock,
        patch.object(
            config_flow, "retrieve_token", side_effect=_raise
        ) as config_flow_mock,
    ):
        yield {"scrypted": scrypted_mock, "config_flow": config_flow_mock}


@pytest.fixture
def mock_retrieve_token_runtime_error():
    """Patch retrieve_token to raise RuntimeError."""

    async def _raise(*args, **kwargs):
        raise RuntimeError("boom")

    with (
        patch.object(scrypted, "retrieve_token", side_effect=_raise) as scrypted_mock,
        patch.object(
            config_flow, "retrieve_token", side_effect=_raise
        ) as config_flow_mock,
    ):
        yield {"scrypted": scrypted_mock, "config_flow": config_flow_mock}


@pytest.fixture
def mock_panel_lifecycle(mock_unregister_lovelace_resource, mock_forward_entry_setups):
    """Mock panel registration/unregistration with state tracking for reload tests."""
    registered_panels = []
    removed_panels = []

    def register_panel(*args, **kwargs):
        panel_path = kwargs.get("frontend_url_path")
        if panel_path in registered_panels:
            raise ValueError(f"Overwriting panel {panel_path}")
        registered_panels.append(panel_path)

    def remove_panel(hass, panel_name):
        if panel_name in registered_panels:
            registered_panels.remove(panel_name)
        removed_panels.append(panel_name)

    with (
        patch.object(
            scrypted, "async_register_built_in_panel", side_effect=register_panel
        ),
        patch.object(scrypted, "async_remove_panel", side_effect=remove_panel),
    ):
        yield {"registered": registered_panels, "removed": removed_panels}
