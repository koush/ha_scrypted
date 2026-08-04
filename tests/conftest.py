"""Shared pytest fixtures for Scrypted tests."""

import copy
import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import loader

pytest_plugins = ["pytest_homeassistant_custom_component"]

import custom_components.scrypted as scrypted  # noqa: E402
from custom_components.scrypted import config_flow, hub  # noqa: E402
from custom_components.scrypted.const import (  # noqa: E402
    CONF_AUTO_REGISTER_RESOURCES,
    CONF_DEVICE_TYPES,
    CONF_ENABLE_ENTITIES,
    CONF_SCRYPTED_NVR,
    DOMAIN,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402

@pytest.fixture(autouse=True)
def _register_scrypted_flow(hass):
    """Register the config flow module so HA can resolve it."""

    module = importlib.import_module("custom_components.scrypted.config_flow")
    hass.data[loader.DATA_COMPONENTS][f"{DOMAIN}.config_flow"] = module


@pytest.fixture(autouse=True)
def _patch_async_get_clientsession():
    """Prevent tests from creating real aiohttp sessions."""

    def _fake_session(hass, *args, **kwargs):
        return SimpleNamespace(loop=hass.loop)

    with (
        patch.object(scrypted, "async_get_clientsession", _fake_session),
        patch.object(config_flow, "async_get_clientsession", _fake_session),
    ):
        yield


@pytest.fixture(autouse=True)
def _patch_retrieve_token():
    """Return a canned token unless a test overrides the patch."""

    async def _fake_retrieve(data, session):
        return "token"

    with (
        patch.object(scrypted, "retrieve_token", _fake_retrieve),
        patch.object(config_flow, "retrieve_token", _fake_retrieve),
    ):
        yield


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
        "detectionClasses": detection_classes if detection_classes is not None else ["person"],
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
            "turnOn", "turnOff", "setBrightness", "setColorTemperature",
            "setHsv", "setRgb", "lock", "unlock", "setFan", "setTemperature",
            "openEntry", "closeEntry", "start", "stop", "pause", "resume", "dock",
        ):
            object.__setattr__(self, command, AsyncMock())
        object.__setattr__(self, "getTemperatureMaxK", AsyncMock(return_value=6500))
        object.__setattr__(self, "getTemperatureMinK", AsyncMock(return_value=2000))
        object.__setattr__(self, "getVideoClips", AsyncMock(return_value=[]))
        object.__setattr__(self, "getVideoClip", AsyncMock(return_value=object()))
        object.__setattr__(self, "getVideoClipThumbnail", AsyncMock(return_value=object()))

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
            createMediaObjectFromUrl=AsyncMock(return_value=object()),
            convertMediaObjectToUrl=AsyncMock(
                return_value="https://scrypted.local:10443/endpoint/@scrypted/nvr/converted"
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
        interfaces=["VideoCamera", "BinarySensor", "MotionSensor", "Intercom", "Online"],
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
        interfaces=["OnOff", "Brightness", "ColorSettingTemperature", "ColorSettingHsv", "Online"],
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
