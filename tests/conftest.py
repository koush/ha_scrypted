"""Shared pytest fixtures for Scrypted tests."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp import ClientConnectorError, web
import pytest

from homeassistant.const import CONF_HOST

pytest_plugins = ["pytest_homeassistant_custom_component"]

from custom_components import scrypted  # noqa: E402
from custom_components.scrypted import config_flow, http  # noqa: E402
from custom_components.scrypted.const import DOMAIN  # noqa: E402

# ---------------------------------------------------------------------------
# Fixture loading helpers
# ---------------------------------------------------------------------------


def load_fixture(name: str) -> dict:
    """Load a JSON fixture file."""
    with open(Path(__file__).parent / "fixtures" / name, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def login_success_fixture() -> dict:
    """Load the successful login response fixture."""
    return load_fixture("login_success.json")


@pytest.fixture
def login_error_not_logged_in_fixture() -> dict:
    """Load the not logged in error fixture."""
    return load_fixture("login_error_not_logged_in.json")


@pytest.fixture
def login_error_incorrect_password_fixture() -> dict:
    """Load the incorrect password error fixture."""
    return load_fixture("login_error_incorrect_password.json")


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow loading this custom integration in tests."""
    yield


@pytest.fixture(autouse=True)
def mock_retrieve_token():
    """Return a canned token unless a test overrides the patch."""

    async def _fake_retrieve(data, session):
        return "token"

    with (
        patch(
            "custom_components.scrypted.retrieve_token", side_effect=_fake_retrieve
        ) as scrypted_mock,
        patch(
            "custom_components.scrypted.config_flow.retrieve_token",
            side_effect=_fake_retrieve,
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
        patch(
            "custom_components.scrypted.retrieve_token", side_effect=_raise
        ) as scrypted_mock,
        patch(
            "custom_components.scrypted.config_flow.retrieve_token",
            side_effect=_raise,
        ) as config_flow_mock,
    ):
        yield {"scrypted": scrypted_mock, "config_flow": config_flow_mock}


@pytest.fixture
def mock_retrieve_token_none():
    """Patch retrieve_token to return None (missing token)."""

    async def _no_token(*args, **kwargs):
        return None

    with (
        patch(
            "custom_components.scrypted.retrieve_token", side_effect=_no_token
        ) as scrypted_mock,
        patch(
            "custom_components.scrypted.config_flow.retrieve_token",
            side_effect=_no_token,
        ) as config_flow_mock,
    ):
        yield {"scrypted": scrypted_mock, "config_flow": config_flow_mock}


@pytest.fixture
def mock_register_lovelace_resource():
    """Patch _async_register_lovelace_resource."""
    with patch(
        "custom_components.scrypted._async_register_lovelace_resource",
        new_callable=AsyncMock,
    ) as mock:
        yield mock


@pytest.fixture
def mock_unregister_lovelace_resource():
    """Patch _async_unregister_lovelace_resource."""
    with patch(
        "custom_components.scrypted._async_unregister_lovelace_resource",
        new_callable=AsyncMock,
    ) as mock:
        yield mock


@pytest.fixture
def mock_register_built_in_panel():
    """Patch async_register_built_in_panel and capture kwargs."""
    captured_kwargs = {}

    def _capture(*args, **kwargs):
        captured_kwargs.update(kwargs)

    with patch(
        "custom_components.scrypted.async_register_built_in_panel",
        side_effect=_capture,
    ) as mock:
        mock.captured_kwargs = captured_kwargs
        yield mock


@pytest.fixture
def mock_remove_panel():
    """Patch async_remove_panel and track removed panels."""
    removed_panels = []

    def _remove(hass, panel_name):
        removed_panels.append(panel_name)

    with patch(
        "custom_components.scrypted.async_remove_panel", side_effect=_remove
    ) as mock:
        mock.removed_panels = removed_panels
        yield mock


@pytest.fixture
def mock_forward_entry_setups(hass):
    """Patch hass.config_entries.async_forward_entry_setups."""
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
        new_callable=AsyncMock,
    ) as mock:
        yield mock


@pytest.fixture
def mock_async_reload(hass):
    """Patch hass.config_entries.async_reload."""
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_reload",
        new_callable=AsyncMock,
    ) as mock:
        yield mock


@pytest.fixture
def mock_flow_async_init(hass):
    """Patch hass.config_entries.flow.async_init."""
    with patch(
        "homeassistant.config_entries.ConfigEntriesFlowManager.async_init",
        new_callable=AsyncMock,
    ) as mock:
        mock.return_value = {"type": "form"}
        yield mock


@pytest.fixture
def mock_async_update_entry(hass):
    """Patch hass.config_entries.async_update_entry."""
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_update_entry"
    ) as mock:
        yield mock


@pytest.fixture
def mock_async_create_notification():
    """Patch async_create for persistent notifications."""
    notifications = {}

    def _create(*args, **kwargs):
        notifications["created"] = (args, kwargs)

    with patch("custom_components.scrypted.async_create", side_effect=_create) as mock:
        mock.notifications = notifications
        yield mock


@pytest.fixture
def mock_scrypted_view():
    """Patch ScryptedView."""
    with patch("custom_components.scrypted.ScryptedView", return_value="view") as mock:
        yield mock


@pytest.fixture
def mock_retrieve_token_client_error():
    """Patch retrieve_token to raise ClientConnectorError."""

    async def _raise(*args, **kwargs):
        raise ClientConnectorError(SimpleNamespace(), OSError())

    with (
        patch(
            "custom_components.scrypted.retrieve_token", side_effect=_raise
        ) as scrypted_mock,
        patch(
            "custom_components.scrypted.config_flow.retrieve_token",
            side_effect=_raise,
        ) as config_flow_mock,
    ):
        yield {"scrypted": scrypted_mock, "config_flow": config_flow_mock}


@pytest.fixture
def mock_retrieve_token_runtime_error():
    """Patch retrieve_token to raise RuntimeError."""

    async def _raise(*args, **kwargs):
        raise RuntimeError("boom")

    with (
        patch(
            "custom_components.scrypted.retrieve_token", side_effect=_raise
        ) as scrypted_mock,
        patch(
            "custom_components.scrypted.config_flow.retrieve_token",
            side_effect=_raise,
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
        patch(
            "custom_components.scrypted.async_register_built_in_panel",
            side_effect=register_panel,
        ),
        patch(
            "custom_components.scrypted.async_remove_panel",
            side_effect=remove_panel,
        ),
    ):
        yield {"registered": registered_panels, "removed": removed_panels}


# ---------------------------------------------------------------------------
# HTTP module test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_web_request():
    """Create a factory for mock aiohttp web.Request objects."""

    def _create_request(
        headers: dict | None = None,
        peername: tuple | None = ("192.168.1.50", 12345),
        host: str = "localhost:8123",
        scheme: str = "https",
    ) -> MagicMock:
        mock_request = MagicMock(spec=web.Request)
        mock_request.headers = headers or {}
        mock_transport = MagicMock()
        mock_transport.get_extra_info.return_value = peername
        mock_request.transport = mock_transport
        mock_request.host = host
        mock_request.url = MagicMock()
        mock_request.url.scheme = scheme
        return mock_request

    return _create_request


@pytest.fixture
def mock_aiohttp_session():
    """Create a mock aiohttp ClientSession."""
    session = MagicMock()
    session.loop = asyncio.get_event_loop()
    return session


@pytest.fixture
async def scrypted_view(hass, mock_aiohttp_session):
    """Create a ScryptedView instance with mocked file loading."""
    hass.data[DOMAIN] = {}

    def _sync_executor(self, func, *args, **kwargs):
        return func(*args, **kwargs)

    with (
        patch.object(
            hass,
            "async_add_executor_job",
            side_effect=lambda func, *args, **kwargs: func(*args, **kwargs),
        ),
        patch("custom_components.scrypted.http.ScryptedView.load_files") as mock_load,
    ):
        view = http.ScryptedView(hass, mock_aiohttp_session)
    # Set up futures with test content
    view.lit_core = asyncio.Future()
    view.lit_core.set_result("lit-core-content")
    view.entrypoint_js = asyncio.Future()
    view.entrypoint_js.set_result("__DOMAIN__ __TOKEN__ js-content")
    view.entrypoint_html = asyncio.Future()
    view.entrypoint_html.set_result("__DOMAIN__ __TOKEN__ core html-content")
    mock_load.assert_called_once()
    return view


@pytest.fixture
def mock_config_entry():
    """Create a factory for mock config entries."""

    def _create_entry(
        host: str = "192.168.1.100:10443",
        data: dict | None = None,
        options: dict | None = None,
    ) -> MagicMock:
        mock_entry = MagicMock()
        mock_entry.data = {CONF_HOST: host, **(data or {})}
        mock_entry.options = options or {}
        return mock_entry

    return _create_entry
