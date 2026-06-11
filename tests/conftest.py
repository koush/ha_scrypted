"""Shared pytest fixtures for Scrypted tests."""

import importlib
from types import SimpleNamespace

import pytest
from homeassistant import loader

pytest_plugins = ["pytest_homeassistant_custom_component"]

import custom_components.scrypted as scrypted  # noqa: E402
from custom_components.scrypted import config_flow  # noqa: E402
from custom_components.scrypted.const import DOMAIN  # noqa: E402

@pytest.fixture(autouse=True)
def _register_scrypted_flow(hass):
    """Register the config flow module so HA can resolve it."""

    module = importlib.import_module("custom_components.scrypted.config_flow")
    hass.data[loader.DATA_COMPONENTS][f"{DOMAIN}.config_flow"] = module


@pytest.fixture(autouse=True)
def _patch_async_get_clientsession(monkeypatch):
    """Prevent tests from creating real aiohttp sessions."""

    def _fake_session(*args, **kwargs):
        return SimpleNamespace()

    monkeypatch.setattr(scrypted, "async_get_clientsession", _fake_session)
    monkeypatch.setattr(config_flow, "async_get_clientsession", _fake_session)


@pytest.fixture(autouse=True)
def _patch_retrieve_token(monkeypatch):
    """Return a canned token unless a test overrides the patch."""

    async def _fake_retrieve(data, session):
        return "token"

    monkeypatch.setattr(scrypted, "retrieve_token", _fake_retrieve)
    monkeypatch.setattr(config_flow, "retrieve_token", _fake_retrieve)


# --- Scrypted SDK fakes -----------------------------------------------------
from unittest.mock import AsyncMock  # noqa: E402


def state(**props):
    """Build a scrypted systemState device entry: {prop: {"value": ...}}."""
    return {key: {"value": value} for key, value in props.items()}


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

    def __getattr__(self, name):
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
    def __init__(self, system_state):
        self.systemManager = FakeSystemManager(system_state)
        self.mediaManager = SimpleNamespace(
            convertMediaObjectToBuffer=AsyncMock(return_value=bytearray(b"fake-jpeg")),
            convertMediaObjectToJSON=AsyncMock(
                return_value={"url": "rtsp://localhost:34567/stream"}
            ),
        )


class FakeTransport:
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
        interfaces=["VideoCamera", "BinarySensor", "MotionSensor", "Online"],
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
}


@pytest.fixture
def system_state():
    """Deep-ish copy so tests can mutate freely."""
    import copy

    return copy.deepcopy(DEFAULT_SYSTEM_STATE)


@pytest.fixture
def fake_sdk(system_state):
    return FakeSDK(system_state)


@pytest.fixture(autouse=True)
def mock_connect_sdk(monkeypatch, fake_sdk):
    """All tests connect to the fake SDK unless they re-patch."""
    from custom_components.scrypted import client as client_module

    transport = FakeTransport()

    async def _fake_connect(hass, host, username, password, plugin_id="@scrypted/core"):
        return transport, fake_sdk

    monkeypatch.setattr(client_module, "async_connect_sdk", _fake_connect)
    return SimpleNamespace(transport=transport, sdk=fake_sdk)
