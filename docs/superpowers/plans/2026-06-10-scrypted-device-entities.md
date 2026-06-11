# Scrypted Device Entities Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mirror Scrypted devices (cameras, motion/object detection, environmental sensors) as Home Assistant entities with push state updates, so users can drive HA automations from Scrypted data.

**Architecture:** A persistent engine.io RPC connection to the Scrypted server (reusing the Scrypted Python plugin-runtime SDK) maintains a live mirror of all device state in `SystemManager.systemState`. A `ScryptedClient` wrapper owns the connection lifecycle and fans state-change events out to entities via HA's dispatcher. Four entity platforms (`camera`, `binary_sensor`, `sensor`, `event`) discover devices by inspecting each device's `interfaces` list and map Scrypted interface properties onto HA entity state.

**Tech Stack:** Python 3.12+, Home Assistant custom integration, `python-engineio[asyncio_client]`, Scrypted Python SDK (vendored via symlinks now, published package later), `pytest-homeassistant-custom-component`.

---

## Background you must understand before starting

### How the Scrypted Python SDK works

The SDK is **not yet published**. It lives in the Scrypted main repo (checked out at `/Users/raman/projects/scrypted`) and is symlinked into this repo at `vendor/scrypted_client/` (already done — see Task 1). The relevant pieces:

- `plugin_remote.py` — `SystemManager`, `DeviceManager`, `MediaManager`, `PluginRemote`, `DeviceProxy`. This is the same code Scrypted Python *plugins* run; reused as a client over engine.io.
- `rpc.py` / `rpc_reader.py` — the RPC peer protocol.
- `scrypted_python/scrypted_sdk/types.py` — `ScryptedInterface`, `ScryptedDeviceType`, `ScryptedInterfaceProperty`, `ScryptedMimeTypes`, `ObjectsDetected`, etc. (all enums verified against `TYPES_VERSION = "0.5.52"`).
- The reference connection code is `/Users/raman/projects/scrypted/packages/python-client/test.py`. **Never import `test.py`** — it starts an event loop at module level. We copy/adapt its `EioRpcTransport` and `connect_scrypted_client` into `client.py`.

Key SDK facts (verified by reading the source):

1. `systemState` is `dict[device_id, dict[property_name, {"value": Any, ...}]]`. Device ids are stable GUID strings.
2. `systemManager.getDeviceById(id)` returns a `DeviceProxy`. Reading `proxy.motionDetected` (any name in `ScryptedInterfaceProperty`) is a **local, synchronous** dict lookup into `systemState`. Calling `await proxy.takePicture()` (any name in `ScryptedInterfaceMethods`) is an **async RPC** to the server.
3. `systemManager.listen(callback)` — local registry; `callback(device_id, event_details, value)` fires for every **state/property change** of every device (`event_details` is a dict: `eventId`, `eventTime`, `eventInterface`, `property`, `mixinId`). Stateless events (e.g. `ObjectsDetected`) do **not** reach system listeners.
4. `systemManager.listenDevice(id, "ObjectDetector", callback)` — registers a **server-side** subscription; `callback(device, event_details, event_data)` fires with `ObjectsDetected` payloads. Returns an `EventListenerRegister` whose `removeListener()` must be called on teardown (it is fire-and-forget async internally; calling it synchronously is fine).
5. `mediaManager.convertMediaObjectToBuffer(media_object, "image/jpeg")` → `bytearray` of a JPEG. `mediaManager.convertMediaObjectToJSON(media_object, ScryptedMimeTypes.FFmpegInput.value)` → dict with a `url` key (usually an `rtsp://` rebroadcast URL).
6. Login: `POST {base_url}/login` with JSON `{"username": ..., "password": ...}` returns `{"authorization": "..."}`. That header value authenticates the engine.io connection at path `/endpoint/@scrypted/core/engine.io/api/`.

### Existing integration structure

- `__init__.py` sets up an iframe panel + HTTP proxy. Entry **data** holds `CONF_HOST` (`"ip"` or `"ip:port"`, default port 10443), `CONF_USERNAME`, `CONF_PASSWORD`, `CONF_NAME`, `CONF_ICON`. Entry **options** hold `CONF_AUTO_REGISTER_RESOURCES`, `CONF_SCRYPTED_NVR` (defaults injected by `_async_ensure_entry_options`).
- `hass.data[DOMAIN][token] = config_entry` is the existing storage shape — **keep it** (http proxy and token sensor depend on it). New runtime objects go on `config_entry.runtime_data`.
- Only `Platform.SENSOR` exists today (a token sensor). Note `async_unload_entry` currently never calls `async_unload_platforms` — Task 5 fixes that.
- Tests use `pytest-homeassistant-custom-component`; `tests/conftest.py` already auto-patches `retrieve_token` and `async_get_clientsession`.

### Device → entity mapping philosophy

Discovery is **interface-driven**: for each device id in `systemState`, look at the `interfaces` list (a `list[str]` of `ScryptedInterface` values) and instantiate one entity per matching entity description. Devices whose `type` is plumbing (plugins, providers, automations) are excluded entirely. The same device commonly matches several platforms (a camera is `camera` + motion `binary_sensor` + battery `sensor` + object-detection `event`); they all attach to one HA device-registry device keyed `(DOMAIN, f"{entry_id}_{device_id}")`.

## File structure

| File | Status | Responsibility |
|---|---|---|
| `vendor/scrypted_client/*` | created | Symlinks to SDK modules in the scrypted repo (dev only) |
| `custom_components/scrypted/sdk_compat.py` | create | Make SDK importable (published pkg → vendor fallback); re-export SDK names |
| `custom_components/scrypted/client.py` | create | engine.io transport, `async_connect_sdk()`, `ScryptedClient` lifecycle + dispatcher fan-out |
| `custom_components/scrypted/entity.py` | create | `ScryptedDeviceEntity` base, description mixin, discovery helper |
| `custom_components/scrypted/binary_sensor.py` | create | Boolean state properties (motion, audio, flood, …) |
| `custom_components/scrypted/sensor.py` | modify | Keep token sensor; add device sensors (temperature, battery, …) |
| `custom_components/scrypted/camera.py` | create | Snapshot + RTSP stream camera entities |
| `custom_components/scrypted/event.py` | create | Object-detection + doorbell-press event entities |
| `custom_components/scrypted/const.py` | modify | New option key, dispatcher signal templates, excluded device types |
| `custom_components/scrypted/__init__.py` | modify | Create/teardown `ScryptedClient`, hub device, forward platforms, fix unload |
| `custom_components/scrypted/config_flow.py` | modify | `enable_entities` option in options flow |
| `custom_components/scrypted/strings.json` + `translations/en.json` | modify | Label for new option |
| `custom_components/scrypted/manifest.json` | modify | Add `python-engineio` requirement |
| `scripts/dev_connect.py` | create | Manual end-to-end connection check against a real server |
| `tests/conftest.py` | modify | Fake SDK (system manager, devices, media manager), auto-mocked connect |
| `tests/test_client.py` | create | Client lifecycle, dispatch, reconnect tests |
| `tests/test_binary_sensor.py` / `test_sensor.py` / `test_camera.py` / `test_event.py` | create/modify | Platform tests |

---

### Task 1: Vendored SDK shim (`sdk_compat.py`)

The symlinks in `vendor/scrypted_client/` already exist (each `*.py` links into `/Users/raman/projects/scrypted/server/python/`, and `scrypted_python` links to `/Users/raman/projects/scrypted/sdk/types/scrypted_python`). They are relative links assuming `scrypted` and `ha_scrypted` are sibling directories.

**Files:**
- Create: `custom_components/scrypted/sdk_compat.py`
- Create: `vendor/README.md`
- Modify: `requirements_dev.txt`
- Test: `tests/test_sdk_compat.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sdk_compat.py
"""Tests for the SDK import shim."""


def test_sdk_imports():
    """The shim exposes the SDK regardless of install mechanism."""
    from custom_components.scrypted import sdk_compat

    assert sdk_compat.ScryptedInterface.MotionSensor.value == "MotionSensor"
    assert sdk_compat.ScryptedInterfaceProperty.motionDetected.value == "motionDetected"
    assert sdk_compat.ScryptedMimeTypes.FFmpegInput.value == "x-scrypted/x-ffmpeg-input"
    # Runtime pieces used by client.py
    assert hasattr(sdk_compat, "plugin_remote")
    assert hasattr(sdk_compat, "rpc_reader")
    assert hasattr(sdk_compat, "ScryptedStatic")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/pytest tests/test_sdk_compat.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'custom_components.scrypted.sdk_compat'`

- [ ] **Step 3: Write the shim**

```python
# custom_components/scrypted/sdk_compat.py
"""Import shim for the Scrypted Python SDK.

The SDK is not published to PyPI yet. Try the installed package first, then
fall back to the repo-local vendored symlinks (vendor/scrypted_client) that
point into a sibling checkout of the scrypted main repo.

When the SDK is published, delete the fallback and add the package to
manifest.json requirements instead.
"""
from __future__ import annotations

import sys
from pathlib import Path


def _ensure_sdk_importable() -> None:
    try:
        import scrypted_python  # noqa: F401

        return
    except ImportError:
        pass
    vendor = Path(__file__).resolve().parents[2] / "vendor" / "scrypted_client"
    if vendor.is_dir() and str(vendor) not in sys.path:
        sys.path.insert(0, str(vendor))


_ensure_sdk_importable()

import plugin_remote  # noqa: E402
import rpc_reader  # noqa: E402
from plugin_remote import (  # noqa: E402
    DeviceManager,
    MediaManager,
    PluginRemote,
    SystemManager,
)
from scrypted_python.scrypted_sdk import ScryptedStatic  # noqa: E402
from scrypted_python.scrypted_sdk.types import (  # noqa: E402
    ScryptedDeviceType,
    ScryptedInterface,
    ScryptedInterfaceProperty,
    ScryptedMimeTypes,
)

__all__ = [
    "DeviceManager",
    "MediaManager",
    "PluginRemote",
    "ScryptedDeviceType",
    "ScryptedInterface",
    "ScryptedInterfaceProperty",
    "ScryptedMimeTypes",
    "ScryptedStatic",
    "SystemManager",
    "plugin_remote",
    "rpc_reader",
]
```

- [ ] **Step 4: Create `vendor/README.md`**

```markdown
# Vendored Scrypted Python SDK

`scrypted_client/` contains symlinks into a sibling checkout of
https://github.com/koush/scrypted (expected at `../scrypted` relative to this
repo). This mirrors `packages/python-client` in that repo, plus the extra
`server/python` modules that `plugin_remote.py` imports transitively
(`cluster_labels`, `cluster_setup`, `plugin_console`, `plugin_pip`,
`plugin_volume`, `plugin_repl`).

`custom_components/scrypted/sdk_compat.py` adds this directory to `sys.path`
when the published SDK package is not installed. Recreate the links with:

    mkdir -p vendor/scrypted_client && cd vendor/scrypted_client
    for f in plugin_remote.py rpc.py rpc_reader.py cluster_labels.py \
             cluster_setup.py plugin_console.py plugin_pip.py \
             plugin_volume.py plugin_repl.py; do
      ln -sf ../../../scrypted/server/python/$f $f
    done
    ln -sfn ../../../scrypted/sdk/types/scrypted_python scrypted_python
```

- [ ] **Step 5: Add `python-engineio` to dev requirements**

Append to `requirements_dev.txt`:

```text
python-engineio[asyncio_client]>=4.9.0
```

Run: `./venv/bin/pip install "python-engineio[asyncio_client]>=4.9.0"`

- [ ] **Step 6: Run test to verify it passes**

Run: `./venv/bin/pytest tests/test_sdk_compat.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add vendor custom_components/scrypted/sdk_compat.py tests/test_sdk_compat.py requirements_dev.txt
git commit -m "feat: vendor scrypted python SDK with import shim"
```

---

### Task 2: Constants and options plumbing

**Files:**
- Modify: `custom_components/scrypted/const.py`
- Modify: `custom_components/scrypted/__init__.py` (only `_OPTION_DEFAULTS`)
- Modify: `custom_components/scrypted/config_flow.py` (options flow)
- Modify: `custom_components/scrypted/strings.json`, `custom_components/scrypted/translations/en.json`
- Test: `tests/test_config_flow.py`

- [ ] **Step 1: Write the failing test** (append to `tests/test_config_flow.py`)

```python
async def test_options_flow_includes_enable_entities(hass):
    """Options flow exposes and persists the enable_entities flag."""
    from custom_components.scrypted.const import (
        CONF_AUTO_REGISTER_RESOURCES,
        CONF_ENABLE_ENTITIES,
        CONF_SCRYPTED_NVR,
        DOMAIN,
    )
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": "1.2.3.4", "username": "u", "password": "p", "name": "Scrypted", "icon": "mdi:memory"},
        options={CONF_AUTO_REGISTER_RESOURCES: False, CONF_SCRYPTED_NVR: False, CONF_ENABLE_ENTITIES: True},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "form"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_AUTO_REGISTER_RESOURCES: False,
            CONF_SCRYPTED_NVR: False,
            CONF_ENABLE_ENTITIES: False,
        },
    )
    assert result["type"] == "create_entry"
    assert result["data"][CONF_ENABLE_ENTITIES] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/pytest tests/test_config_flow.py::test_options_flow_includes_enable_entities -v`
Expected: FAIL with `ImportError: cannot import name 'CONF_ENABLE_ENTITIES'`

- [ ] **Step 3: Extend `const.py`** (replace file contents)

```python
"""Constants for the Scrypted integration."""

DOMAIN = "scrypted"
CONF_SCRYPTED_NVR = "scrypted_nvr"
CONF_AUTO_REGISTER_RESOURCES = "auto_register_resources"
CONF_ENABLE_ENTITIES = "enable_entities"

# Dispatcher signals. format() args noted per signal.
SIGNAL_DEVICE_UPDATE = "scrypted_{}_device_update_{}"  # entry_id, device_id
SIGNAL_NEW_DEVICE = "scrypted_{}_new_device"  # entry_id; payload: device_id
SIGNAL_CONNECTION = "scrypted_{}_connection"  # entry_id; payload: connected bool

# Scrypted device types that are server plumbing, never user-facing devices.
EXCLUDED_DEVICE_TYPES = {
    "API",
    "Automation",
    "Bridge",
    "Builtin",
    "DataSource",
    "DeviceProvider",
    "Internal",
    "Internet",
    "LLM",
    "Network",
    "Notifier",
    "Program",
    "Scene",
}
```

- [ ] **Step 4: Wire the option default into `__init__.py`**

In `custom_components/scrypted/__init__.py`, add `CONF_ENABLE_ENTITIES` to the const import and extend `_OPTION_DEFAULTS`:

```python
from .const import (
    CONF_AUTO_REGISTER_RESOURCES,
    CONF_ENABLE_ENTITIES,
    CONF_SCRYPTED_NVR,
    DOMAIN,
)

_OPTION_DEFAULTS = {
    CONF_AUTO_REGISTER_RESOURCES: False,
    CONF_SCRYPTED_NVR: False,
    CONF_ENABLE_ENTITIES: True,
}
```

- [ ] **Step 5: Extend the options flow in `config_flow.py`**

Import `CONF_ENABLE_ENTITIES` from `.const`. In `ScryptedOptionsFlowHandler.async_step_general`, persist the new key and add it to the schema:

```python
        if user_input is not None:
            data = {
                **self.config_entry.options,
                CONF_AUTO_REGISTER_RESOURCES: user_input[CONF_AUTO_REGISTER_RESOURCES],
                CONF_SCRYPTED_NVR: user_input[CONF_SCRYPTED_NVR],
                CONF_ENABLE_ENTITIES: user_input[CONF_ENABLE_ENTITIES],
            }
            return self.async_create_entry(data=data)
```

and in the schema (after the `current_nvr` lookup):

```python
        current_entities = self.config_entry.options.get(CONF_ENABLE_ENTITIES, True)

        return self.async_show_form(
            step_id="general",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_AUTO_REGISTER_RESOURCES, default=current_auto
                    ): bool,
                    vol.Required(CONF_SCRYPTED_NVR, default=current_nvr): bool,
                    vol.Required(CONF_ENABLE_ENTITIES, default=current_entities): bool,
                }
            ),
        )
```

- [ ] **Step 6: Add option labels**

In `strings.json` and `translations/en.json`, find the `options` → `step` → `general` → `data` object and add (keep existing keys):

```json
"enable_entities": "Create entities for Scrypted devices (cameras, sensors, events)"
```

- [ ] **Step 7: Run the tests**

Run: `./venv/bin/pytest tests/test_config_flow.py -v`
Expected: all PASS (new test plus pre-existing options-flow tests)

- [ ] **Step 8: Commit**

```bash
git add custom_components/scrypted tests/test_config_flow.py
git commit -m "feat: add enable_entities option"
```

---

### Task 3: Low-level engine.io connection (`client.py` part 1)

Adapted from `packages/python-client/test.py`. No unit tests for the raw transport (it needs a live server); correctness is covered by `scripts/dev_connect.py` (manual) and by everything above it being injectable.

**Files:**
- Create: `custom_components/scrypted/client.py`
- Create: `scripts/dev_connect.py`

- [ ] **Step 1: Write the transport and connect function**

```python
# custom_components/scrypted/client.py
"""Engine.io RPC client for the Scrypted server."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
import engineio

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import SIGNAL_CONNECTION, SIGNAL_DEVICE_UPDATE, SIGNAL_NEW_DEVICE
from .sdk_compat import ScryptedStatic, plugin_remote, rpc_reader

_LOGGER = logging.getLogger(__name__)

CONNECT_TIMEOUT = 30
RECONNECT_INITIAL_DELAY = 5
RECONNECT_MAX_DELAY = 300
PLUGIN_ID = "@scrypted/core"


class ScryptedConnectionError(Exception):
    """Raised when the Scrypted engine.io connection cannot be established."""


def get_base_url(host: str) -> str:
    """Return https base url for a configured host ('ip' or 'ip:port')."""
    ipport = host.split(":")
    if len(ipport) > 2:
        raise ScryptedConnectionError(f"invalid Scrypted host: {host}")
    ip = ipport[0]
    port = ipport[1] if len(ipport) == 2 else "10443"
    return f"https://{ip}:{port}"


class EioRpcTransport(rpc_reader.RpcTransport):
    """RpcTransport over an engine.io connection (from scrypted python-client)."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        super().__init__()
        self.eio = engineio.AsyncClient(ssl_verify=False)
        self.loop = loop
        self.write_error: Exception | None = None
        self.read_queue: asyncio.Queue = asyncio.Queue()
        self.write_queue: asyncio.Queue = asyncio.Queue()
        self._send_task: asyncio.Task | None = None

        @self.eio.on("message")
        def on_message(data):
            self.read_queue.put_nowait(data)

        self._send_task = loop.create_task(self.send_loop())

    async def read(self):
        return await self.read_queue.get()

    async def send_loop(self):
        while True:
            data = await self.write_queue.get()
            try:
                await self.eio.send(data)
            except Exception as e:  # noqa: BLE001 - any send failure kills the link
                self.write_error = e
                break

    def writeBuffer(self, buffer, reject):
        if self.write_error:
            if reject:
                reject(self.write_error)
            return
        self.write_queue.put_nowait(buffer)

    def writeJSON(self, json, reject):
        return self.writeBuffer(json, reject)

    async def close(self) -> None:
        """Tear the transport down."""
        if self._send_task:
            self._send_task.cancel()
        try:
            await self.eio.disconnect()
        except Exception:  # noqa: BLE001 - best effort teardown
            _LOGGER.debug("Error disconnecting engine.io client", exc_info=True)


async def async_connect_sdk(
    hass: HomeAssistant,
    host: str,
    username: str,
    password: str,
    plugin_id: str = PLUGIN_ID,
) -> tuple[EioRpcTransport, ScryptedStatic]:
    """Login and establish the engine.io RPC session. Returns (transport, sdk)."""
    base_url = get_base_url(host)
    session = async_get_clientsession(hass, verify_ssl=False)

    try:
        async with session.post(
            f"{base_url}/login",
            json={"username": username, "password": password},
            raise_for_status=True,
        ) as response:
            login_response = await response.json()
    except aiohttp.ClientError as err:
        raise ScryptedConnectionError(f"Login to {base_url} failed: {err}") from err

    if "authorization" not in login_response:
        raise ScryptedConnectionError(
            f"Login to {base_url} did not return an authorization header "
            f"(response keys: {sorted(login_response)})"
        )

    loop = hass.loop
    transport = EioRpcTransport(loop)
    try:
        await transport.eio.connect(
            base_url,
            headers={"Authorization": login_response["authorization"]},
            engineio_path=f"/endpoint/{plugin_id}/engine.io/api/",
        )
    except engineio.exceptions.ConnectionError as err:
        await transport.close()
        raise ScryptedConnectionError(f"engine.io connect failed: {err}") from err

    # Bootstrap the plugin-remote handshake (mirrors python-client/test.py).
    ret: asyncio.Future[ScryptedStatic] = loop.create_future()
    peer, peer_read_loop = await rpc_reader.prepare_peer_readloop(loop, transport)
    peer.params["print"] = _LOGGER.debug

    def get_remote(api, plugin_id_, host_info):
        remote = plugin_remote.PluginRemote(peer, api, plugin_id_, host_info, loop)
        wrapped = remote.setSystemState

        async def remote_set_system_state(system_state):
            await wrapped(system_state)

            async def resolve():
                sdk = ScryptedStatic()
                sdk.api = api
                sdk.remote = remote
                sdk.systemManager = plugin_remote.SystemManager(
                    api, remote.systemState
                )
                sdk.deviceManager = plugin_remote.DeviceManager(
                    remote.nativeIds, sdk.systemManager
                )
                sdk.mediaManager = plugin_remote.MediaManager(
                    await api.getMediaManager()
                )
                if not ret.done():
                    ret.set_result(sdk)

            loop.create_task(resolve())

        remote.setSystemState = remote_set_system_state
        return remote

    peer.params["getRemote"] = get_remote
    loop.create_task(peer_read_loop())

    try:
        sdk = await asyncio.wait_for(asyncio.shield(ret), CONNECT_TIMEOUT)
    except TimeoutError as err:
        await transport.close()
        raise ScryptedConnectionError(
            f"Timed out waiting for Scrypted system state from {base_url}"
        ) from err
    return transport, sdk
```

- [ ] **Step 2: Write the manual verification script**

```python
# scripts/dev_connect.py
"""Manual end-to-end check of the engine.io client against a real server.

Usage:
    SCRYPTED_HOST=192.168.1.5:10443 SCRYPTED_USERNAME=u SCRYPTED_PASSWORD=p \
        ./venv/bin/python scripts/dev_connect.py
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vendor" / "scrypted_client"))


async def main():
    from unittest.mock import MagicMock

    # Minimal HomeAssistant stand-in for async_connect_sdk.
    import aiohttp

    from custom_components.scrypted import client as client_mod

    hass = MagicMock()
    hass.loop = asyncio.get_running_loop()
    session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False))
    client_mod.async_get_clientsession = lambda *_, **__: session

    transport, sdk = await client_mod.async_connect_sdk(
        hass,
        os.environ["SCRYPTED_HOST"],
        os.environ["SCRYPTED_USERNAME"],
        os.environ["SCRYPTED_PASSWORD"],
    )
    state = sdk.systemManager.getSystemState()
    print(f"Connected. {len(state)} devices:")
    for device_id in state:
        device = sdk.systemManager.getDeviceById(device_id)
        print(f"  {device_id}: {device.name} type={device.type} interfaces={device.interfaces}")
    await transport.close()
    await session.close()


asyncio.run(main())
```

- [ ] **Step 3: Verify it imports and (if a server is available) connects**

Run: `./venv/bin/python -c "import sys; sys.path.insert(0, 'vendor/scrypted_client'); from custom_components.scrypted import client; print('ok')"`
Expected: `ok`

Optional live check: run `scripts/dev_connect.py` with real credentials; expect a device listing.

- [ ] **Step 4: Commit**

```bash
git add custom_components/scrypted/client.py scripts/dev_connect.py
git commit -m "feat: low-level scrypted engine.io client"
```

---

### Task 4: `ScryptedClient` lifecycle wrapper (`client.py` part 2)

**Files:**
- Modify: `custom_components/scrypted/client.py`
- Modify: `tests/conftest.py` (fake SDK fixtures)
- Test: `tests/test_client.py`

- [ ] **Step 1: Add fake SDK infrastructure to `tests/conftest.py`** (append; these fakes mimic the real `plugin_remote` shapes — `{prop: {"value": ...}}` state, `DeviceProxy.__getattr__` semantics)

```python
# --- Scrypted SDK fakes -----------------------------------------------------
from unittest.mock import AsyncMock


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
            self, "getObjectTypes", AsyncMock(return_value={"classes": ["person", "car"]})
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

        class _Register:
            def removeListener(reg_self):
                self._system_listeners.remove(callback)

        return _Register()

    def listenDevice(self, device_id, event_interface, callback):
        self.device_listeners[(device_id, event_interface)] = callback

        class _Register:
            def removeListener(reg_self):
                self.device_listeners.pop((device_id, event_interface), None)

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

        class _Eio:
            def on(eio_self, event):
                def decorator(fn):
                    self.handlers[event] = fn
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
```

Also extend the existing imports at the top of `conftest.py` if needed (`pytest`, `SimpleNamespace` are already imported).

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_client.py
"""Tests for ScryptedClient."""
import pytest
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.scrypted.client import ScryptedClient
from custom_components.scrypted.const import (
    DOMAIN,
    SIGNAL_DEVICE_UPDATE,
    SIGNAL_NEW_DEVICE,
)


@pytest.fixture
def entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": "1.2.3.4", "username": "u", "password": "p"},
    )
    entry.add_to_hass(hass)
    return entry


async def test_connect_populates_devices(hass, entry, fake_sdk):
    client = ScryptedClient(hass, entry)
    await client.async_connect()
    assert client.connected
    assert "cam1" in client.device_ids
    await client.async_disconnect()
    assert not client.connected


async def test_state_change_dispatches_update(hass, entry, fake_sdk):
    client = ScryptedClient(hass, entry)
    await client.async_connect()

    updates = []
    async_dispatcher_connect(
        hass,
        SIGNAL_DEVICE_UPDATE.format(entry.entry_id, "cam1"),
        lambda details, value: updates.append((details["property"], value)),
    )
    fake_sdk.systemManager.set_property("cam1", "motionDetected", True)
    await hass.async_block_till_done()
    assert updates == [("motionDetected", True)]
    await client.async_disconnect()


async def test_unknown_device_dispatches_new_device(hass, entry, fake_sdk):
    client = ScryptedClient(hass, entry)
    await client.async_connect()

    new = []
    async_dispatcher_connect(
        hass,
        SIGNAL_NEW_DEVICE.format(entry.entry_id),
        lambda device_id: new.append(device_id),
    )
    fake_sdk.systemManager.systemState["new1"] = {
        "name": {"value": "New Device"},
        "type": {"value": "Sensor"},
        "interfaces": {"value": ["FloodSensor"]},
    }
    fake_sdk.systemManager.set_property("new1", "flooded", False)
    await hass.async_block_till_done()
    assert new == ["new1"]
    await client.async_disconnect()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `./venv/bin/pytest tests/test_client.py -v`
Expected: FAIL with `ImportError: cannot import name 'ScryptedClient'`

- [ ] **Step 4: Implement `ScryptedClient`** (append to `client.py`)

```python
class ScryptedClient:
    """Owns the SDK connection for a config entry and fans out events."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.sdk: ScryptedStatic | None = None
        self.transport: EioRpcTransport | None = None
        self.connected = False
        self._known_ids: set[str] = set()
        self._closing = False
        self._reconnect_task: asyncio.Task | None = None

    @property
    def host(self) -> str:
        return self.entry.data[CONF_HOST]

    @property
    def device_ids(self) -> list[str]:
        if not self.sdk:
            return []
        return list(self.sdk.systemManager.getSystemState())

    async def async_connect(self) -> None:
        """Connect and register listeners. Raises ScryptedConnectionError."""
        self.transport, self.sdk = await async_connect_sdk(
            self.hass,
            self.host,
            self.entry.data[CONF_USERNAME],
            self.entry.data.get(CONF_PASSWORD, ""),
        )
        self.sdk.systemManager.listen(self._on_system_event)

        @self.transport.eio.on("disconnect")
        def on_disconnect(*args):
            self._handle_disconnect()

        self._known_ids = set(self.device_ids)
        self.connected = True
        async_dispatcher_send(
            self.hass, SIGNAL_CONNECTION.format(self.entry.entry_id), True
        )

    async def async_disconnect(self) -> None:
        """Shut down for good (entry unload)."""
        self._closing = True
        if self._reconnect_task:
            self._reconnect_task.cancel()
            self._reconnect_task = None
        self.connected = False
        if self.transport:
            await self.transport.close()
        self.transport = None
        self.sdk = None

    @callback
    def _on_system_event(self, device_id: str, event_details: dict, value: Any) -> None:
        """System listener: runs on the HA event loop (engine.io read task)."""
        if device_id not in self._known_ids:
            self._known_ids.add(device_id)
            async_dispatcher_send(
                self.hass, SIGNAL_NEW_DEVICE.format(self.entry.entry_id), device_id
            )
        async_dispatcher_send(
            self.hass,
            SIGNAL_DEVICE_UPDATE.format(self.entry.entry_id, device_id),
            event_details,
            value,
        )

    @callback
    def _handle_disconnect(self) -> None:
        if self._closing:
            return
        _LOGGER.warning("Scrypted %s disconnected; reconnecting", self.host)
        self.connected = False
        async_dispatcher_send(
            self.hass, SIGNAL_CONNECTION.format(self.entry.entry_id), False
        )
        if not self._reconnect_task or self._reconnect_task.done():
            self._reconnect_task = self.entry.async_create_background_task(
                self.hass, self._reconnect_loop(), name="scrypted_reconnect"
            )

    async def _reconnect_loop(self) -> None:
        delay = RECONNECT_INITIAL_DELAY
        while not self._closing and not self.connected:
            try:
                if self.transport:
                    await self.transport.close()
                await self.async_connect()
                _LOGGER.info("Scrypted %s reconnected", self.host)
                return
            except ScryptedConnectionError as err:
                _LOGGER.debug("Scrypted reconnect failed: %s", err)
                await asyncio.sleep(delay)
                delay = min(delay * 2, RECONNECT_MAX_DELAY)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `./venv/bin/pytest tests/test_client.py tests/test_sdk_compat.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add custom_components/scrypted/client.py tests/conftest.py tests/test_client.py
git commit -m "feat: ScryptedClient connection lifecycle with dispatcher fan-out"
```

---

### Task 5: Integration wiring in `__init__.py`

**Files:**
- Modify: `custom_components/scrypted/__init__.py`
- Test: `tests/test_init.py` (append)

- [ ] **Step 1: Write the failing test** (append to `tests/test_init.py`; mirror the file's existing entry-setup helper style — it already sets up entries with data/options dicts)

```python
async def test_setup_entry_creates_client_and_unloads(hass):
    """Entities enabled: client connects on setup and disconnects on unload."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.scrypted.const import CONF_ENABLE_ENTITIES, DOMAIN

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
            "auto_register_resources": False,
            "scrypted_nvr": False,
            CONF_ENABLE_ENTITIES: True,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.runtime_data.client is not None
    assert entry.runtime_data.client.connected

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.client.connected is False


async def test_setup_entry_entities_disabled(hass):
    """Entities disabled: no client, panel-only setup still succeeds."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.scrypted.const import CONF_ENABLE_ENTITIES, DOMAIN

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
            "auto_register_resources": False,
            "scrypted_nvr": False,
            CONF_ENABLE_ENTITIES: False,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.client is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./venv/bin/pytest tests/test_init.py -v`
Expected: new tests FAIL (`runtime_data` missing); pre-existing tests still pass.

- [ ] **Step 3: Modify `__init__.py`**

Add imports and a runtime-data container near the top:

```python
from dataclasses import dataclass

from homeassistant.helpers import device_registry as dr

from .client import ScryptedClient, ScryptedConnectionError, get_base_url
from .const import (
    CONF_AUTO_REGISTER_RESOURCES,
    CONF_ENABLE_ENTITIES,
    CONF_SCRYPTED_NVR,
    DOMAIN,
)


@dataclass
class ScryptedRuntimeData:
    """Objects for this config entry's lifetime."""

    token: str
    client: ScryptedClient | None


type ScryptedConfigEntry = ConfigEntry[ScryptedRuntimeData]

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.CAMERA,
    Platform.EVENT,
    Platform.SENSOR,
]
```

In `async_setup_entry`, after `hass.data.setdefault(DOMAIN, {})[token] = config_entry` and before the panel registration, add:

```python
    client: ScryptedClient | None = None
    if config_entry.options.get(CONF_ENABLE_ENTITIES, True):
        client = ScryptedClient(hass, config_entry)
        try:
            await client.async_connect()
        except ScryptedConnectionError as err:
            # Token retrieval succeeded so the server is up; engine.io failing
            # is unexpected — retry the whole entry setup.
            raise ConfigEntryNotReady(f"Scrypted engine.io connect failed: {err}") from err

        device_registry = dr.async_get(hass)
        device_registry.async_get_or_create(
            config_entry_id=config_entry.entry_id,
            identifiers={(DOMAIN, config_entry.entry_id)},
            manufacturer="Scrypted",
            name=config_entry.data[CONF_NAME],
            configuration_url=get_base_url(config_entry.data[CONF_HOST]),
        )

    config_entry.runtime_data = ScryptedRuntimeData(token=token, client=client)
```

`CONF_HOST` needs importing from `homeassistant.const` alongside the existing const imports.

In `async_unload_entry`, replace the body with platform unload + client teardown (keep existing token/panel cleanup):

```python
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

    await _async_unregister_lovelace_resource(hass, token, config_entry.entry_id)

    hass.data[DOMAIN].pop(token)
    if not hass.data[DOMAIN]:
        hass.data.pop(DOMAIN)
    async_remove_panel(hass, f"{DOMAIN}_{token}")
    return True
```

Also update `manifest.json` requirements:

```json
  "requirements": ["python-engineio>=4.9.0"],
```

- [ ] **Step 4: Run the full test suite**

Run: `./venv/bin/pytest tests/ -v`
Expected: PASS. If pre-existing `test_init.py`/`test_sensor.py` tests fail because setup now forwards more platforms, the `mock_connect_sdk` autouse fixture covers the client; fix any remaining failures by adjusting expectations (e.g. entity counts), never by weakening the new code.

- [ ] **Step 5: Commit**

```bash
git add custom_components/scrypted/__init__.py custom_components/scrypted/manifest.json tests/test_init.py
git commit -m "feat: wire ScryptedClient into entry setup/unload"
```

---

### Task 6: Entity base class and discovery helper (`entity.py`)

**Files:**
- Create: `custom_components/scrypted/entity.py`
- Test: covered indirectly by platform tests (Tasks 7-10); a direct unit test for the discovery filter below.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_entity.py
"""Tests for discovery helpers."""
from custom_components.scrypted.entity import device_matches


def test_device_matches_interface(fake_sdk):
    assert device_matches(fake_sdk, "cam1", "MotionSensor")
    assert not device_matches(fake_sdk, "leak1", "MotionSensor")


def test_excluded_types_never_match(fake_sdk):
    # plugin1 has Online but is type API (excluded plumbing)
    assert not device_matches(fake_sdk, "plugin1", "Online")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/pytest tests/test_entity.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `entity.py`**

```python
# custom_components/scrypted/entity.py
"""Base entity for Scrypted devices."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .client import ScryptedClient
from .const import (
    DOMAIN,
    EXCLUDED_DEVICE_TYPES,
    SIGNAL_CONNECTION,
    SIGNAL_DEVICE_UPDATE,
)
from .sdk_compat import ScryptedInterface


@dataclass(frozen=True, kw_only=True)
class ScryptedEntityDescriptionMixin:
    """Scrypted-specific description fields.

    interface: the ScryptedInterface that must be present for discovery.
    state_property: the systemState property backing this entity's value.
    value_fn: converts the raw scrypted value to the HA native value.
    """

    interface: str
    state_property: str | None = None
    value_fn: Callable[[Any], Any] = lambda value: value


def device_matches(sdk, device_id: str, interface: str) -> bool:
    """Return True if the device should produce an entity for interface."""
    device = sdk.systemManager.getDeviceById(device_id)
    if device is None:
        return False
    if (device.type or "Unknown") in EXCLUDED_DEVICE_TYPES:
        return False
    return interface in (device.interfaces or [])


class ScryptedDeviceEntity(Entity):
    """Common behavior: device info, availability, push updates."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(
        self,
        client: ScryptedClient,
        entry: ConfigEntry,
        device_id: str,
        description,
    ) -> None:
        self.client = client
        self.entry = entry
        self.device_id = device_id
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{device_id}_{description.key}"

        device = client.sdk.systemManager.getDeviceById(device_id)
        info = device.info or {}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{device_id}")},
            name=device.name,
            manufacturer=info.get("manufacturer"),
            model=info.get("model"),
            sw_version=info.get("version") or info.get("firmware"),
            serial_number=info.get("serialNumber"),
            suggested_area=device.room,
            via_device=(DOMAIN, entry.entry_id),
            configuration_url=info.get("managementUrl"),
        )

    @property
    def device(self):
        """Live DeviceProxy; property reads are local dict lookups."""
        if not self.client.sdk:
            return None
        return self.client.sdk.systemManager.getDeviceById(self.device_id)

    @property
    def raw_value(self) -> Any:
        """Raw scrypted value of this entity's backing property."""
        device = self.device
        prop = self.entity_description.state_property
        if device is None or prop is None:
            return None
        return getattr(device, prop)

    @property
    def available(self) -> bool:
        if not self.client.connected:
            return False
        device = self.device
        if device is None:
            return False
        if (
            ScryptedInterface.Online.value in (device.interfaces or [])
            and device.online is False
        ):
            return False
        return True

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_DEVICE_UPDATE.format(self.entry.entry_id, self.device_id),
                self._handle_device_update,
            )
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_CONNECTION.format(self.entry.entry_id),
                self._handle_connection_change,
            )
        )

    @callback
    def _handle_device_update(self, event_details: dict, value: Any) -> None:
        self.async_write_ha_state()

    @callback
    def _handle_connection_change(self, connected: bool) -> None:
        self.async_write_ha_state()
```

- [ ] **Step 4: Run tests**

Run: `./venv/bin/pytest tests/test_entity.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add custom_components/scrypted/entity.py tests/test_entity.py
git commit -m "feat: scrypted base entity and discovery helper"
```

---

### Task 7: Binary sensor platform

**Files:**
- Create: `custom_components/scrypted/binary_sensor.py`
- Test: `tests/test_binary_sensor.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_binary_sensor.py
"""Tests for scrypted binary sensors."""
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.scrypted.const import CONF_ENABLE_ENTITIES, DOMAIN


async def setup_entry(hass):
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
            "auto_register_resources": False,
            "scrypted_nvr": False,
            CONF_ENABLE_ENTITIES: True,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_motion_sensor_created_and_updates(hass, fake_sdk):
    await setup_entry(hass)

    state = hass.states.get("binary_sensor.front_door_cam_motion")
    assert state is not None
    assert state.state == "off"

    fake_sdk.systemManager.set_property("cam1", "motionDetected", True)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.front_door_cam_motion").state == "on"


async def test_flood_sensor_created(hass, fake_sdk):
    await setup_entry(hass)
    state = hass.states.get("binary_sensor.basement_leak_flooded")
    assert state is not None
    assert state.state == "off"


async def test_excluded_plugin_has_no_entities(hass, fake_sdk):
    await setup_entry(hass)
    # plugin1 (type API) must not create a connectivity sensor
    assert not [
        s for s in hass.states.async_all("binary_sensor") if "some_plugin" in s.entity_id
    ]


async def test_new_device_added_at_runtime(hass, fake_sdk):
    await setup_entry(hass)
    fake_sdk.systemManager.systemState["new1"] = {
        "name": {"value": "Garage Leak"},
        "type": {"value": "Sensor"},
        "info": {"value": {}},
        "interfaces": {"value": ["FloodSensor"]},
    }
    fake_sdk.systemManager.set_property("new1", "flooded", True)
    await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.garage_leak_flooded")
    assert state is not None
    assert state.state == "on"


async def test_offline_device_unavailable(hass, fake_sdk):
    await setup_entry(hass)
    fake_sdk.systemManager.set_property("cam1", "online", False)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.front_door_cam_motion").state == "unavailable"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./venv/bin/pytest tests/test_binary_sensor.py -v`
Expected: FAIL (no entities created — platform module missing)

- [ ] **Step 3: Implement the platform**

```python
# custom_components/scrypted/binary_sensor.py
"""Binary sensors for Scrypted device states."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import SIGNAL_NEW_DEVICE
from .entity import (
    ScryptedDeviceEntity,
    ScryptedEntityDescriptionMixin,
    device_matches,
)


@dataclass(frozen=True, kw_only=True)
class ScryptedBinarySensorDescription(
    BinarySensorEntityDescription, ScryptedEntityDescriptionMixin
):
    """Describes a scrypted binary sensor."""


BINARY_SENSORS: tuple[ScryptedBinarySensorDescription, ...] = (
    ScryptedBinarySensorDescription(
        key="motion",
        name="Motion",
        interface="MotionSensor",
        state_property="motionDetected",
        device_class=BinarySensorDeviceClass.MOTION,
    ),
    ScryptedBinarySensorDescription(
        key="binary_state",
        name="Binary state",
        interface="BinarySensor",
        state_property="binaryState",
    ),
    ScryptedBinarySensorDescription(
        key="audio",
        name="Sound",
        interface="AudioSensor",
        state_property="audioDetected",
        device_class=BinarySensorDeviceClass.SOUND,
    ),
    ScryptedBinarySensorDescription(
        key="occupancy",
        name="Occupancy",
        interface="OccupancySensor",
        state_property="occupied",
        device_class=BinarySensorDeviceClass.OCCUPANCY,
    ),
    ScryptedBinarySensorDescription(
        key="flooded",
        name="Flooded",
        interface="FloodSensor",
        state_property="flooded",
        device_class=BinarySensorDeviceClass.MOISTURE,
    ),
    ScryptedBinarySensorDescription(
        key="entry_open",
        name="Entry open",
        interface="EntrySensor",
        state_property="entryOpen",
        device_class=BinarySensorDeviceClass.DOOR,
        # entryOpen can be True/False/'jammed'
        value_fn=lambda value: value is True,
    ),
    ScryptedBinarySensorDescription(
        key="power",
        name="Power",
        interface="PowerSensor",
        state_property="powerDetected",
        device_class=BinarySensorDeviceClass.POWER,
    ),
    ScryptedBinarySensorDescription(
        key="online",
        name="Online",
        interface="Online",
        state_property="online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ScryptedBinarySensorDescription(
        key="tampered",
        name="Tampered",
        interface="TamperSensor",
        state_property="tampered",
        device_class=BinarySensorDeviceClass.TAMPER,
        entity_category=EntityCategory.DIAGNOSTIC,
        # tampered is a TamperState string or falsy
        value_fn=lambda value: bool(value),
    ),
    ScryptedBinarySensorDescription(
        key="charging",
        name="Charging",
        interface="Charger",
        state_property="chargeState",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda value: value in ("charging", "trickle"),
    ),
    ScryptedBinarySensorDescription(
        key="sleeping",
        name="Sleeping",
        interface="Sleep",
        state_property="sleeping",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up scrypted binary sensors."""
    client = config_entry.runtime_data.client
    if client is None:
        return
    known: set[tuple[str, str]] = set()

    @callback
    def _add_for_device(device_id: str) -> None:
        entities = []
        for description in BINARY_SENSORS:
            if (device_id, description.key) in known:
                continue
            if not device_matches(client.sdk, device_id, description.interface):
                continue
            known.add((device_id, description.key))
            entities.append(
                ScryptedBinarySensor(client, config_entry, device_id, description)
            )
        if entities:
            async_add_entities(entities)

    for device_id in client.device_ids:
        _add_for_device(device_id)

    config_entry.async_on_unload(
        async_dispatcher_connect(
            hass, SIGNAL_NEW_DEVICE.format(config_entry.entry_id), _add_for_device
        )
    )


class ScryptedBinarySensor(ScryptedDeviceEntity, BinarySensorEntity):
    """A boolean scrypted device property."""

    entity_description: ScryptedBinarySensorDescription

    @property
    def is_on(self) -> bool | None:
        value = self.raw_value
        if value is None:
            return None
        return bool(self.entity_description.value_fn(value))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./venv/bin/pytest tests/test_binary_sensor.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add custom_components/scrypted/binary_sensor.py tests/test_binary_sensor.py
git commit -m "feat: binary sensor platform for scrypted device states"
```

---

### Task 8: Sensor platform (device sensors alongside the token sensor)

**Files:**
- Modify: `custom_components/scrypted/sensor.py`
- Test: `tests/test_sensor.py` (append)

- [ ] **Step 1: Write the failing tests** (append to `tests/test_sensor.py`, reusing the `setup_entry` helper pattern from `tests/test_binary_sensor.py` — import it: `from tests.test_binary_sensor import setup_entry`)

```python
async def test_device_sensors_created(hass, fake_sdk):
    await setup_entry(hass)

    temp = hass.states.get("sensor.basement_leak_temperature")
    assert temp is not None
    assert temp.state == "21.5"
    assert temp.attributes["device_class"] == "temperature"

    battery = hass.states.get("sensor.front_door_cam_battery")
    assert battery is not None
    assert battery.state == "80"


async def test_sensor_updates_on_event(hass, fake_sdk):
    await setup_entry(hass)
    fake_sdk.systemManager.set_property("leak1", "temperature", 25.0)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.basement_leak_temperature").state == "25.0"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./venv/bin/pytest tests/test_sensor.py -v`
Expected: new tests FAIL (entities missing); existing token sensor tests PASS.

- [ ] **Step 3: Extend `sensor.py`** (keep `ScryptedTokenSensor` exactly as is; replace the module imports and `async_setup_entry`, then append the new code)

```python
"""Sensors for the Scrypted integration."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    CONCENTRATION_PARTS_PER_MILLION,
    CONF_HOST,
    LIGHT_LUX,
    PERCENTAGE,
    EntityCategory,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_NEW_DEVICE
from .entity import (
    ScryptedDeviceEntity,
    ScryptedEntityDescriptionMixin,
    device_matches,
)


@dataclass(frozen=True, kw_only=True)
class ScryptedSensorDescription(
    SensorEntityDescription, ScryptedEntityDescriptionMixin
):
    """Describes a scrypted sensor."""


SENSORS: tuple[ScryptedSensorDescription, ...] = (
    ScryptedSensorDescription(
        key="temperature",
        name="Temperature",
        interface="Thermometer",
        state_property="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ScryptedSensorDescription(
        key="humidity",
        name="Humidity",
        interface="HumiditySensor",
        state_property="humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ScryptedSensorDescription(
        key="battery",
        name="Battery",
        interface="Battery",
        state_property="batteryLevel",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ScryptedSensorDescription(
        key="ambient_light",
        name="Ambient light",
        interface="AmbientLightSensor",
        state_property="ambientLight",
        device_class=SensorDeviceClass.ILLUMINANCE,
        native_unit_of_measurement=LIGHT_LUX,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ScryptedSensorDescription(
        key="luminance",
        name="Luminance",
        interface="LuminanceSensor",
        state_property="luminance",
        device_class=SensorDeviceClass.ILLUMINANCE,
        native_unit_of_measurement=LIGHT_LUX,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ScryptedSensorDescription(
        key="ultraviolet",
        name="UV index",
        interface="UltravioletSensor",
        state_property="ultraviolet",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ScryptedSensorDescription(
        key="co2",
        name="CO2",
        interface="CO2Sensor",
        state_property="co2ppm",
        device_class=SensorDeviceClass.CO2,
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ScryptedSensorDescription(
        key="pm25",
        name="PM2.5",
        interface="PM25Sensor",
        state_property="pm25Density",
        device_class=SensorDeviceClass.PM25,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ScryptedSensorDescription(
        key="pm10",
        name="PM10",
        interface="PM10Sensor",
        state_property="pm10Density",
        device_class=SensorDeviceClass.PM10,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ScryptedSensorDescription(
        key="voc",
        name="VOC",
        interface="VOCSensor",
        state_property="vocDensity",
        device_class=SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ScryptedSensorDescription(
        key="nox",
        name="NOx",
        interface="NOXSensor",
        state_property="noxDensity",
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ScryptedSensorDescription(
        key="air_quality",
        name="Air quality",
        interface="AirQualitySensor",
        state_property="airQuality",
        device_class=SensorDeviceClass.ENUM,
        options=["Excellent", "Good", "Fair", "Inferior", "Poor", "Unknown"],
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Scrypted sensors from config entry."""
    token = next(
        token
        for token, entry in hass.data[DOMAIN].items()
        if entry.entry_id == config_entry.entry_id
    )
    async_add_entities([ScryptedTokenSensor(config_entry, token)])

    client = config_entry.runtime_data.client
    if client is None:
        return
    known: set[tuple[str, str]] = set()

    @callback
    def _add_for_device(device_id: str) -> None:
        entities = []
        for description in SENSORS:
            if (device_id, description.key) in known:
                continue
            if not device_matches(client.sdk, device_id, description.interface):
                continue
            known.add((device_id, description.key))
            entities.append(
                ScryptedSensor(client, config_entry, device_id, description)
            )
        if entities:
            async_add_entities(entities)

    for device_id in client.device_ids:
        _add_for_device(device_id)

    config_entry.async_on_unload(
        async_dispatcher_connect(
            hass, SIGNAL_NEW_DEVICE.format(config_entry.entry_id), _add_for_device
        )
    )


class ScryptedSensor(ScryptedDeviceEntity, SensorEntity):
    """A numeric/enum scrypted device property."""

    entity_description: ScryptedSensorDescription

    @property
    def native_value(self):
        value = self.raw_value
        if value is None:
            return None
        return self.entity_description.value_fn(value)
```

- [ ] **Step 4: Run tests**

Run: `./venv/bin/pytest tests/test_sensor.py -v`
Expected: PASS (token sensor tests and new device sensor tests)

- [ ] **Step 5: Commit**

```bash
git add custom_components/scrypted/sensor.py tests/test_sensor.py
git commit -m "feat: device sensors (temperature, battery, air quality, etc.)"
```

---

### Task 9: Camera platform

**Files:**
- Create: `custom_components/scrypted/camera.py`
- Test: `tests/test_camera.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_camera.py
"""Tests for scrypted cameras."""
from homeassistant.components.camera import async_get_image

from tests.test_binary_sensor import setup_entry


async def test_camera_created(hass, fake_sdk):
    await setup_entry(hass)
    state = hass.states.get("camera.front_door_cam")
    assert state is not None


async def test_camera_snapshot(hass, fake_sdk):
    await setup_entry(hass)
    image = await async_get_image(hass, "camera.front_door_cam")
    assert image.content == b"fake-jpeg"
    # Snapshot prefers takePicture when Camera interface present
    fake_sdk.systemManager.getDeviceById("cam1").takePicture.assert_awaited()


async def test_camera_stream_source_rewrites_localhost(hass, fake_sdk):
    await setup_entry(hass)
    from homeassistant.components.camera import get_camera_from_entity_id

    camera = get_camera_from_entity_id(hass, "camera.front_door_cam")
    source = await camera.stream_source()
    # fake mediaManager returns rtsp://localhost:34567/stream; localhost must
    # be rewritten to the configured scrypted host
    assert source == "rtsp://1.2.3.4:34567/stream"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./venv/bin/pytest tests/test_camera.py -v`
Expected: FAIL (camera entity missing)

- [ ] **Step 3: Implement the platform**

```python
# custom_components/scrypted/camera.py
"""Camera entities for Scrypted video devices."""
from __future__ import annotations

import logging

from yarl import URL

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import ScryptedClient
from .const import SIGNAL_NEW_DEVICE
from .entity import ScryptedDeviceEntity, device_matches
from .sdk_compat import ScryptedInterface, ScryptedMimeTypes

_LOGGER = logging.getLogger(__name__)

# A real EntityDescription so Entity internals (entity_registry_enabled_default,
# icon resolution, etc.) behave; cameras are not table-driven.
CAMERA_DESCRIPTION = EntityDescription(key="camera", name=None)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up scrypted cameras."""
    client = config_entry.runtime_data.client
    if client is None:
        return
    known: set[str] = set()

    @callback
    def _add_for_device(device_id: str) -> None:
        if device_id in known:
            return
        if not device_matches(
            client.sdk, device_id, ScryptedInterface.VideoCamera.value
        ):
            return
        known.add(device_id)
        async_add_entities(
            [ScryptedCamera(client, config_entry, device_id, CAMERA_DESCRIPTION)]
        )

    for device_id in client.device_ids:
        _add_for_device(device_id)

    config_entry.async_on_unload(
        async_dispatcher_connect(
            hass, SIGNAL_NEW_DEVICE.format(config_entry.entry_id), _add_for_device
        )
    )


class ScryptedCamera(ScryptedDeviceEntity, Camera):
    """A scrypted VideoCamera device."""

    _attr_name = None

    def __init__(
        self,
        client: ScryptedClient,
        entry: ConfigEntry,
        device_id: str,
        description,
    ) -> None:
        Camera.__init__(self)
        ScryptedDeviceEntity.__init__(self, client, entry, device_id, description)
        self._attr_supported_features = CameraEntityFeature.STREAM

    @property
    def is_recording(self) -> bool:
        device = self.device
        if device is None:
            return False
        if ScryptedInterface.VideoRecorder.value in (device.interfaces or []):
            return bool(device.recordingActive)
        return False

    @property
    def motion_detection_enabled(self) -> bool:
        device = self.device
        return bool(
            device
            and ScryptedInterface.MotionSensor.value in (device.interfaces or [])
        )

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Snapshot via Camera.takePicture, falling back to the video stream."""
        device = self.device
        if device is None or not self.client.sdk:
            return None
        try:
            if ScryptedInterface.Camera.value in (device.interfaces or []):
                media_object = await device.takePicture()
            else:
                media_object = await device.getVideoStream()
            buffer = await self.client.sdk.mediaManager.convertMediaObjectToBuffer(
                media_object, "image/jpeg"
            )
        except Exception:  # noqa: BLE001 - snapshot failures must not blow up HA
            _LOGGER.exception("Failed to fetch snapshot for %s", self.entity_id)
            return None
        return bytes(buffer)

    async def stream_source(self) -> str | None:
        """RTSP URL from scrypted's rebroadcast (FFmpegInput)."""
        device = self.device
        if device is None or not self.client.sdk:
            return None
        try:
            media_object = await device.getVideoStream()
            ffmpeg_input = await self.client.sdk.mediaManager.convertMediaObjectToJSON(
                media_object, ScryptedMimeTypes.FFmpegInput.value
            )
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Failed to resolve stream for %s", self.entity_id)
            return None
        url = (ffmpeg_input or {}).get("url")
        if not url or not url.startswith("rtsp"):
            _LOGGER.debug(
                "No usable RTSP url for %s (got %s); install/enable the "
                "scrypted rebroadcast plugin",
                self.entity_id,
                url,
            )
            return None
        return self._rewrite_stream_host(url)

    def _rewrite_stream_host(self, url: str) -> str:
        """Rebroadcast URLs are server-local; swap in the configured host."""
        parsed = URL(url)
        if parsed.host in ("localhost", "127.0.0.1", "0.0.0.0"):
            host_ip = self.client.host.split(":")[0]
            return str(parsed.with_host(host_ip))
        return url
```

- [ ] **Step 4: Run tests**

Run: `./venv/bin/pytest tests/test_camera.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add custom_components/scrypted/camera.py tests/test_camera.py
git commit -m "feat: camera platform with snapshot and RTSP stream"
```

---

### Task 10: Event platform (object detection + doorbell)

**Files:**
- Create: `custom_components/scrypted/event.py`
- Test: `tests/test_event.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_event.py
"""Tests for scrypted event entities."""
from tests.test_binary_sensor import setup_entry


async def test_object_detection_event(hass, fake_sdk):
    await setup_entry(hass)

    state = hass.states.get("event.front_door_cam_object_detected")
    assert state is not None
    assert "person" in state.attributes["event_types"]

    fake_sdk.systemManager.fire_device_event(
        "cam1",
        "ObjectDetector",
        {
            "detections": [
                {"className": "person", "score": 0.92, "zones": ["porch"]},
            ],
            "timestamp": 1,
        },
    )
    await hass.async_block_till_done()

    state = hass.states.get("event.front_door_cam_object_detected")
    assert state.attributes["event_type"] == "person"
    assert state.attributes["score"] == 0.92


async def test_unknown_detection_class_extends_event_types(hass, fake_sdk):
    await setup_entry(hass)
    fake_sdk.systemManager.fire_device_event(
        "cam1",
        "ObjectDetector",
        {"detections": [{"className": "raccoon", "score": 0.5}], "timestamp": 1},
    )
    await hass.async_block_till_done()
    state = hass.states.get("event.front_door_cam_object_detected")
    assert state.attributes["event_type"] == "raccoon"


async def test_doorbell_press_event(hass, fake_sdk):
    await setup_entry(hass)

    state = hass.states.get("event.doorbell_doorbell")
    assert state is not None

    fake_sdk.systemManager.set_property("bell1", "binaryState", True)
    await hass.async_block_till_done()
    state = hass.states.get("event.doorbell_doorbell")
    assert state.attributes["event_type"] == "pressed"

    # Releasing must not fire another event
    last_changed = state.last_changed
    fake_sdk.systemManager.set_property("bell1", "binaryState", False)
    await hass.async_block_till_done()
    assert hass.states.get("event.doorbell_doorbell").last_changed == last_changed
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./venv/bin/pytest tests/test_event.py -v`
Expected: FAIL (event entities missing)

- [ ] **Step 3: Implement the platform**

```python
# custom_components/scrypted/event.py
"""Event entities for stateless Scrypted events."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.event import (
    EventDeviceClass,
    EventEntity,
    EventEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import ScryptedClient
from .const import SIGNAL_CONNECTION, SIGNAL_NEW_DEVICE
from .entity import ScryptedDeviceEntity, device_matches
from .sdk_compat import ScryptedInterface

_LOGGER = logging.getLogger(__name__)

OBJECT_DETECTED = EventEntityDescription(
    key="object_detected",
    name="Object detected",
    device_class=EventDeviceClass.MOTION,
)
DOORBELL = EventEntityDescription(
    key="doorbell",
    name="Doorbell",
    device_class=EventDeviceClass.DOORBELL,
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up scrypted event entities."""
    client = config_entry.runtime_data.client
    if client is None:
        return
    known: set[tuple[str, str]] = set()

    @callback
    def _add_for_device(device_id: str) -> None:
        entities: list[EventEntity] = []
        device = client.sdk.systemManager.getDeviceById(device_id)
        if device is None:
            return
        if (
            device_matches(client.sdk, device_id, ScryptedInterface.ObjectDetector.value)
            and (device_id, OBJECT_DETECTED.key) not in known
        ):
            known.add((device_id, OBJECT_DETECTED.key))
            entities.append(
                ScryptedObjectDetectionEvent(
                    client, config_entry, device_id, OBJECT_DETECTED
                )
            )
        if (
            device.type == "Doorbell"
            and device_matches(client.sdk, device_id, ScryptedInterface.BinarySensor.value)
            and (device_id, DOORBELL.key) not in known
        ):
            known.add((device_id, DOORBELL.key))
            entities.append(
                ScryptedDoorbellEvent(client, config_entry, device_id, DOORBELL)
            )
        if entities:
            async_add_entities(entities)

    for device_id in client.device_ids:
        _add_for_device(device_id)

    config_entry.async_on_unload(
        async_dispatcher_connect(
            hass, SIGNAL_NEW_DEVICE.format(config_entry.entry_id), _add_for_device
        )
    )


class ScryptedObjectDetectionEvent(ScryptedDeviceEntity, EventEntity):
    """Fires when the scrypted ObjectDetector reports detections.

    Stateless ObjectsDetected payloads do not reach system listeners, so this
    entity owns a per-device server-side subscription (listenDevice) and must
    re-register it after every reconnect.
    """

    _attr_event_types: list[str] = []

    def __init__(self, client, entry, device_id, description) -> None:
        super().__init__(client, entry, device_id, description)
        self._attr_event_types = []
        self._unregister = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        await self._async_load_event_types()
        self._register_listener()
        # Re-register the server-side listener after reconnects.
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_CONNECTION.format(self.entry.entry_id),
                self._handle_reconnect,
            )
        )

    async def async_will_remove_from_hass(self) -> None:
        self._remove_listener()

    async def _async_load_event_types(self) -> None:
        device = self.device
        try:
            object_types = await device.getObjectTypes()
            classes = list((object_types or {}).get("classes") or [])
        except Exception:  # noqa: BLE001 - some detectors don't implement this
            _LOGGER.debug("getObjectTypes failed for %s", self.device_id, exc_info=True)
            classes = []
        self._attr_event_types = classes or ["motion"]

    def _register_listener(self) -> None:
        if not self.client.sdk:
            return
        self._unregister = self.client.sdk.systemManager.listenDevice(
            self.device_id,
            ScryptedInterface.ObjectDetector.value,
            self._on_objects_detected,
        )

    def _remove_listener(self) -> None:
        if self._unregister:
            self._unregister.removeListener()
            self._unregister = None

    @callback
    def _handle_reconnect(self, connected: bool) -> None:
        if connected:
            self._remove_listener()
            self._register_listener()

    def _on_objects_detected(self, device, event_details: dict, data: Any) -> None:
        """Runs on the HA loop via the engine.io read task."""
        detections = (data or {}).get("detections") or []
        seen: set[str] = set()
        for detection in detections:
            class_name = detection.get("className")
            if not class_name or class_name in seen:
                continue
            seen.add(class_name)
            if class_name not in self._attr_event_types:
                # event_types is fixed at trigger time; extend for unknown classes
                self._attr_event_types = [*self._attr_event_types, class_name]
            self._trigger_event(
                class_name,
                {
                    "label": detection.get("label"),
                    "score": detection.get("score"),
                    "zones": detection.get("zones"),
                    "detection_id": (data or {}).get("detectionId"),
                },
            )
        if seen:
            self.async_write_ha_state()


class ScryptedDoorbellEvent(ScryptedDeviceEntity, EventEntity):
    """Fires on doorbell button presses (binaryState rising edge)."""

    _attr_event_types = ["pressed"]

    @callback
    def _handle_device_update(self, event_details: dict, value: Any) -> None:
        if event_details.get("property") == "binaryState" and value:
            self._trigger_event("pressed")
        self.async_write_ha_state()
```

- [ ] **Step 4: Run tests**

Run: `./venv/bin/pytest tests/test_event.py -v`
Expected: PASS

- [ ] **Step 5: Run the entire suite**

Run: `./venv/bin/pytest tests/ -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add custom_components/scrypted/event.py tests/test_event.py
git commit -m "feat: event entities for object detection and doorbell presses"
```

---

### Task 11: Docs and cleanup

**Files:**
- Modify: `README.md`, `TODO.md`
- Modify: `custom_components/scrypted/manifest.json` (version bump)

- [ ] **Step 1: Update `README.md`** — add a section:

```markdown
## Device entities

When *Create entities for Scrypted devices* is enabled (default), the
integration connects to the Scrypted server over its engine.io RPC API and
creates entities for discovered devices:

- **Camera** — snapshots and RTSP streams for `VideoCamera` devices. Streams
  require the Scrypted rebroadcast plugin (bundled with most camera plugins).
- **Binary sensor** — motion, audio, occupancy, flood, entry, power,
  connectivity, tamper, charging.
- **Sensor** — temperature, humidity, battery, illuminance, UV, CO2,
  PM2.5/PM10, VOC, NOx, air quality.
- **Event** — object detection (`person`, `car`, … from the detector's
  reported classes) and doorbell presses, usable as automation triggers.

State updates are pushed; no polling. Entities reconnect automatically if the
server restarts.

### Development

The Scrypted Python SDK is not yet on PyPI. For development, `vendor/scrypted_client`
symlinks into a sibling checkout of the scrypted repo (see `vendor/README.md`).
`scripts/dev_connect.py` smoke-tests connectivity against a real server.
```

- [ ] **Step 2: Update `TODO.md`** — add follow-ups:

```markdown
- Replace vendored SDK symlinks with the published scrypted client package in
  manifest.json requirements once it ships.
- Device removal: entities for deleted scrypted devices currently linger as
  unavailable until the entry is reloaded.
- PTZ support (`PanTiltZoom` interface) on cameras.
- Lock / switch / light platforms for controllable scrypted devices.
- WebRTC streaming (`RTCSignalingChannel`) instead of RTSP rewrite.
```

- [ ] **Step 3: Bump manifest version** to `0.1.0`.

- [ ] **Step 4: Final verification**

Run: `./venv/bin/pytest tests/ -v && ./venv/bin/python -m ruff check custom_components/ 2>/dev/null || true`
Expected: tests PASS; fix any ruff findings in files you touched.

- [ ] **Step 5: Commit**

```bash
git add README.md TODO.md custom_components/scrypted/manifest.json
git commit -m "docs: document device entities and dev setup"
```

---

## Known risks / decisions made

1. **Auth**: the engine.io connection re-logs-in with username/password (`POST /login` → `authorization` header) exactly like the upstream `python-client/test.py`, rather than reusing the proxy token. This is the proven path; if it 401s on some setups, fall back to `{"Authorization": f"Bearer {token}"}` with the token from `retrieve_token`.
2. **Setup failure mode**: engine.io failure raises `ConfigEntryNotReady` (HA retries). Token retrieval already gates setup on server reachability, so this only adds risk if engine.io specifically is broken; users can disable the `enable_entities` option to bypass.
3. **Stream URLs**: `FFmpegInput.url` is usually an `rtsp://localhost:<port>` rebroadcast URL; we rewrite `localhost` to the configured host. If the rebroadcast plugin binds to localhost only, streams won't work remotely — snapshots still will. WebRTC is the long-term fix (TODO).
4. **`plugin_remote` import side effects**: importing it pulls in `plugin_pip`, `plugin_volume`, etc. They are import-safe (verified), but pin behavior may change upstream; `sdk_compat.py` is the single choke point to adapt.
5. **Event-loop integration**: all SDK callbacks fire on `hass.loop` (the engine.io read task runs there), so `async_dispatcher_send` / `_trigger_event` calls from callbacks are safe without `call_soon_threadsafe`.
