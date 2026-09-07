"""Shared pytest fixtures for Scrypted tests."""

import asyncio
from contextlib import contextmanager
import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp import ClientConnectorError, web
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

pytest_plugins = ["pytest_homeassistant_custom_component"]

from custom_components.scrypted import http, hub  # noqa: E402
from custom_components.scrypted.const import (  # noqa: E402
    CONF_AUTO_REGISTER_RESOURCES,
    CONF_DEVICE_TYPES,
    CONF_ENABLE_ENTITIES,
    CONF_SCRYPTED_NVR,
    DOMAIN,
)

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


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow loading this custom integration in tests."""
    yield


# ---------------------------------------------------------------------------
# retrieve_token patching
# ---------------------------------------------------------------------------

RETRIEVE_TOKEN_PATCH_TARGETS = (
    "custom_components.scrypted.retrieve_token",
    "custom_components.scrypted.config_flow.retrieve_token",
)


@contextmanager
def _patch_retrieve_token(side_effect):
    """Patch retrieve_token at every import site with the given side effect."""
    with (
        patch(
            RETRIEVE_TOKEN_PATCH_TARGETS[0], side_effect=side_effect
        ) as scrypted_mock,
        patch(RETRIEVE_TOKEN_PATCH_TARGETS[1], side_effect=side_effect) as flow_mock,
    ):
        yield {"scrypted": scrypted_mock, "config_flow": flow_mock}


def _raise(exc):
    """Return an async side effect that raises ``exc``."""

    async def _side_effect(*args, **kwargs):
        raise exc

    return _side_effect


@pytest.fixture
def patch_retrieve_token():
    """Return a context manager factory for patching retrieve_token."""
    return _patch_retrieve_token


@pytest.fixture(autouse=True)
def mock_retrieve_token():
    """Return a canned token unless a test overrides the patch."""

    async def _fake_retrieve(data, session):
        return "token"

    with _patch_retrieve_token(_fake_retrieve) as mocks:
        yield mocks


@pytest.fixture
def mock_retrieve_token_error():
    """Patch retrieve_token to raise ValueError (invalid credentials)."""
    with _patch_retrieve_token(_raise(ValueError())) as mocks:
        yield mocks


@pytest.fixture
def mock_retrieve_token_none():
    """Patch retrieve_token to return None (missing token)."""

    async def _no_token(*args, **kwargs):
        return None

    with _patch_retrieve_token(_no_token) as mocks:
        yield mocks


@pytest.fixture
def mock_retrieve_token_client_error():
    """Patch retrieve_token to raise ClientConnectorError."""
    exc = ClientConnectorError(SimpleNamespace(), OSError())
    with _patch_retrieve_token(_raise(exc)) as mocks:
        yield mocks


@pytest.fixture
def mock_retrieve_token_runtime_error():
    """Patch retrieve_token to raise RuntimeError."""
    with _patch_retrieve_token(_raise(RuntimeError("boom"))) as mocks:
        yield mocks


# ---------------------------------------------------------------------------
# Reusable patch fixtures for common mocks
# ---------------------------------------------------------------------------


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
    with patch("homeassistant.config_entries.ConfigEntries.async_update_entry") as mock:
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
    return MagicMock()


@pytest.fixture
async def scrypted_view(hass, mock_aiohttp_session):
    """Create a ScryptedView instance with mocked file loading."""
    hass.data[DOMAIN] = {}

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


# --- Scrypted SDK fakes -----------------------------------------------------


def state(**props):
    """Build a scrypted systemState device entry: {prop: {"value": ...}}."""
    return {key: {"value": value} for key, value in props.items()}


def video_clip(clip_id, start_time_ms, *, detection_classes=None, with_resources=True):
    """Build a scrypted VideoClip dict as the NVR returns them."""
    clip = {
        "id": clip_id,
        "videoId": clip_id,
        "thumbnailId": clip_id,
        "startTime": start_time_ms,
        "duration": 30000,
        "event": "motion",
        "description": "Motion Event",
        "detectionClasses": detection_classes
        if detection_classes is not None
        else ["person"],
    }
    if with_resources:
        clip["resources"] = {
            "video": {"href": f"/endpoint/@scrypted/nvr/public/{clip_id}.mp4"},
            "thumbnail": {"href": f"/endpoint/@scrypted/nvr/public/{clip_id}.jpg"},
        }
    return clip


class FakeDevice:
    """Mimics plugin_remote.DeviceProxy: local property reads, async methods."""

    def __init__(self, manager, device_id):
        object.__setattr__(self, "_manager", manager)
        object.__setattr__(self, "id", device_id)
        # Async RPC methods, overridable per-test.
        object.__setattr__(self, "takePicture", AsyncMock(return_value=object()))
        object.__setattr__(self, "getVideoStream", AsyncMock(return_value=object()))
        object.__setattr__(
            self,
            "getObjectTypes",
            AsyncMock(return_value={"classes": ["person", "car"]}),
        )
        object.__setattr__(self, "startIntercom", AsyncMock())
        object.__setattr__(self, "stopIntercom", AsyncMock())
        for command in (
            "turnOn",
            "turnOff",
            "setBrightness",
            "setColorTemperature",
            "setHsv",
            "setRgb",
            "lock",
            "unlock",
            "setFan",
            "setTemperature",
            "openEntry",
            "closeEntry",
            "start",
            "stop",
            "pause",
            "resume",
            "dock",
        ):
            object.__setattr__(self, command, AsyncMock())
        object.__setattr__(self, "getTemperatureMaxK", AsyncMock(return_value=6500))
        object.__setattr__(self, "getTemperatureMinK", AsyncMock(return_value=2000))
        object.__setattr__(self, "getVideoClips", AsyncMock(return_value=[]))
        object.__setattr__(self, "getVideoClip", AsyncMock(return_value=object()))
        object.__setattr__(
            self, "getVideoClipThumbnail", AsyncMock(return_value=object())
        )

    def __getattr__(self, name):
        """Read a device property from the manager's system state."""
        device_state = self._manager.systemState.get(self.id) or {}
        prop = device_state.get(name)
        if prop is None:
            return None
        return prop.get("value")


class FakeSystemManager:
    """Mimics plugin_remote.SystemManager."""

    def __init__(self, system_state):
        self.systemState = system_state
        self._system_listeners = []
        self.device_listeners = {}  # (device_id, event_interface) -> callback
        self._devices = {}

    def getSystemState(self):
        return self.systemState

    def getDeviceById(self, device_id):
        if device_id not in self.systemState:
            return None
        if device_id not in self._devices:
            self._devices[device_id] = FakeDevice(self, device_id)
        return self._devices[device_id]

    def listen(self, callback):
        self._system_listeners.append(callback)
        manager = self

        class _Register:
            def removeListener(self):
                manager._system_listeners.remove(callback)

        return _Register()

    def listenDevice(self, device_id, event_interface, callback):
        self.device_listeners[(device_id, event_interface)] = callback
        manager = self

        class _Register:
            def removeListener(self):
                manager.device_listeners.pop((device_id, event_interface), None)

        return _Register()

    # -- test helpers --
    def set_property(self, device_id, prop, value, event_interface=None):
        """Update state and fire system listeners like the real EventRegistry."""
        self.systemState.setdefault(device_id, {})[prop] = {"value": value}
        details = {
            "eventId": "x",
            "eventTime": 0,
            "eventInterface": event_interface,
            "property": prop,
            "mixinId": None,
        }
        for listener in list(self._system_listeners):
            listener(device_id, details, value)

    def fire_device_event(self, device_id, event_interface, value):
        """Fire a stateless event at a listenDevice subscriber."""
        callback = self.device_listeners.get((device_id, event_interface))
        assert callback, f"no listener for {device_id}#{event_interface}"
        details = {
            "eventId": "x",
            "eventTime": 0,
            "eventInterface": event_interface,
            "property": None,
            "mixinId": None,
        }
        callback(self.getDeviceById(device_id), details, value)


class FakeSDK:
    """Mimics the scrypted sdk static object (systemManager and mediaManager)."""

    def __init__(self, system_state):
        self.systemManager = FakeSystemManager(system_state)
        self.mediaManager = SimpleNamespace(
            convertMediaObjectToBuffer=AsyncMock(return_value=bytearray(b"fake-jpeg")),
            convertMediaObjectToJSON=AsyncMock(
                return_value={"url": "rtsp://localhost:34567/stream"}
            ),
            createMediaObjectFromUrl=AsyncMock(return_value=object()),
            convertMediaObjectToUrl=AsyncMock(
                return_value="https://scrypted.local:10443/endpoint/@scrypted/nvr/converted"
            ),
        )


class FakeTransport:
    """Mimics EioRpcTransport, recording registered engine.io handlers."""

    def __init__(self):
        self.handlers = {}
        self.closed = False
        transport = self

        class _Eio:
            def on(self, event):
                def decorator(fn):
                    transport.handlers[event] = fn
                    return fn

                return decorator

        self.eio = _Eio()

    async def close(self):
        self.closed = True


DEFAULT_SYSTEM_STATE = {
    "cam1": state(
        name="Front Door Cam",
        type="Camera",
        room="Porch",
        info={"manufacturer": "Acme", "model": "Cam2000", "version": "1.0"},
        interfaces=[
            "VideoCamera",
            "Camera",
            "MotionSensor",
            "ObjectDetector",
            "Battery",
            "Online",
            "VideoRecorder",
            "VideoClips",
        ],
        motionDetected=False,
        batteryLevel=80,
        online=True,
        recordingActive=True,
    ),
    "bell1": state(
        name="Doorbell",
        type="Doorbell",
        room=None,
        info={},
        interfaces=[
            "VideoCamera",
            "BinarySensor",
            "MotionSensor",
            "Intercom",
            "Online",
        ],
        binaryState=False,
        motionDetected=False,
        online=True,
    ),
    "leak1": state(
        name="Basement Leak",
        type="Sensor",
        room="Basement",
        info={},
        interfaces=["FloodSensor", "Thermometer", "HumiditySensor", "Online"],
        flooded=False,
        temperature=21.5,
        humidity=40,
        online=True,
    ),
    "plugin1": state(
        name="Some Plugin",
        type="API",
        info={},
        interfaces=["Online", "ScryptedPlugin"],
        online=True,
    ),
    "haimport1": state(
        name="Imported HA Light",
        type="Camera",  # type passes the default allowlist on purpose
        info={},
        pluginId="@scrypted/homeassistant",
        interfaces=["VideoCamera", "OnOff", "Online"],
        on=False,
        online=True,
    ),
    "light1": state(
        name="Desk Light",
        type="Light",
        info={},
        interfaces=[
            "OnOff",
            "Brightness",
            "ColorSettingTemperature",
            "ColorSettingHsv",
            "Online",
        ],
        on=False,
        brightness=50,
        colorTemperature=3000,
        hsv={"h": 120, "s": 0.5, "v": 1},
        online=True,
    ),
    "outlet1": state(
        name="Heater Plug",
        type="Outlet",
        info={},
        interfaces=["OnOff", "Online"],
        on=True,
        online=True,
    ),
    "lock1": state(
        name="Side Door",
        type="Lock",
        info={},
        interfaces=["Lock", "Online"],
        lockState="Locked",
        online=True,
    ),
    "fan1": state(
        name="Attic Fan",
        type="Fan",
        info={},
        interfaces=["Fan", "Online"],
        fan={
            "active": True,
            "speed": 2,
            "maxSpeed": 4,
            "mode": "Manual",
            "counterClockwise": False,
            "swing": False,
            "availableModes": ["Manual", "Auto"],
        },
        online=True,
    ),
    "thermo1": state(
        name="Hallway Thermostat",
        type="Thermostat",
        info={},
        interfaces=["TemperatureSetting", "Thermometer", "HumiditySensor", "Online"],
        temperatureSetting={
            "availableModes": ["Off", "Heat", "Cool", "HeatCool"],
            "mode": "Heat",
            "activeMode": "Heat",
            "setpoint": 21,
        },
        temperature=20,
        humidity=40,
        online=True,
    ),
    "garage1": state(
        name="Garage Door",
        type="Garage",
        info={},
        interfaces=["Entry", "EntrySensor", "Online"],
        entryOpen=False,
        online=True,
    ),
    "vac1": state(
        name="Robo Vac",
        type="Vacuum",
        info={},
        interfaces=["StartStop", "Pause", "Dock", "Online"],
        running=False,
        paused=False,
        docked=True,
        online=True,
    ),
}


@pytest.fixture
def system_state():
    """Deep-ish copy so tests can mutate freely."""
    return copy.deepcopy(DEFAULT_SYSTEM_STATE)


@pytest.fixture
def fake_sdk(system_state):
    """Return a fake scrypted SDK backed by the mutable system state."""
    return FakeSDK(system_state)


@pytest.fixture(autouse=True)
def mock_connect_sdk(fake_sdk):
    """All tests connect to the fake SDK unless they re-patch."""
    transport = FakeTransport()

    async def _fake_connect(hass, host, username, password, plugin_id="@scrypted/core"):
        return transport, fake_sdk

    with patch.object(hub, "async_connect_sdk", _fake_connect):
        yield SimpleNamespace(transport=transport, sdk=fake_sdk)


async def setup_entry(hass, device_types=None):
    """Create, add, and fully set up a scrypted config entry."""
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
            CONF_DEVICE_TYPES: device_types or ["Camera", "Doorbell", "Sensor"],
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry
