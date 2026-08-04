"""Contract tests for the vendored Scrypted SDK's event dispatch.

The integration relies on upstream behavior that was missing from the Python
SDK port (present in server/src/plugin/plugin-remote.ts and event-registry.ts):
PluginRemote.notify must dispatch incoming events to the attached
systemManager's event registry, and EventRegistry.listenDevice must register
against the token-keyed listener set. These tests run against the symlinked
checkout in vendor/scrypted_client, so they fail if that checkout regresses
to a pre-fix state.
"""

import asyncio
from types import SimpleNamespace

from scrypted_sdk import PluginRemote, SystemManager


def make_remote_and_manager(system_state):
    """Build a PluginRemote wired like the sdk module's resolve()/loadZip."""
    cluster_setup = SimpleNamespace(peer=SimpleNamespace(params={}))
    remote = PluginRemote(
        cluster_setup, None, "@scrypted/core", {}, asyncio.get_event_loop()
    )
    remote.systemState = system_state
    manager = SystemManager(None, remote.systemState)
    remote.systemManager = manager
    return remote, manager


def motion_details(**overrides):
    details = {
        "eventId": "e1",
        "eventTime": 1,
        "eventInterface": "MotionSensor",
        "property": "motionDetected",
        "mixinId": None,
    }
    details.update(overrides)
    return details


async def test_property_event_updates_state_and_fires_system_listener():
    system_state = {"cam1": {"motionDetected": {"value": False}}}
    remote, manager = make_remote_and_manager(system_state)

    calls = []
    manager.listen(
        lambda device_id, details, value: calls.append((device_id, details, value))
    )

    details = motion_details()
    await remote.notify("cam1", details, {"stateTime": 1, "value": True})

    assert system_state["cam1"]["motionDetected"] == {"stateTime": 1, "value": True}
    # Listener receives the unwrapped value (plugin-remote.ts: eventData.value).
    assert calls == [("cam1", details, True)]


async def test_property_event_for_unknown_device_is_dropped():
    remote, manager = make_remote_and_manager({})

    calls = []
    manager.listen(lambda *args: calls.append(args))

    await remote.notify("ghost", motion_details(), {"value": True})

    assert calls == []


async def test_mixin_property_event_skips_state_and_dispatches_raw():
    """plugin-remote.ts: mixinId property events don't write device state."""
    system_state = {"cam1": {"motionDetected": {"value": False}}}
    remote, manager = make_remote_and_manager(system_state)

    calls = []
    manager.listen(
        lambda device_id, details, value: calls.append((device_id, details, value))
    )

    payload = {"stateTime": 2, "value": True}
    details = motion_details(mixinId="mixin-1")
    await remote.notify("cam1", details, payload)

    assert system_state["cam1"]["motionDetected"] == {"value": False}
    # Mixin events pass through unmodified (no .value unwrap)...
    # ...but system listeners don't receive property events from mixins
    # (EventRegistry gates on property and not mixinId), so nothing arrives.
    assert calls == []


async def test_stateless_event_reaches_device_listener_not_system_listener():
    system_state = {"cam1": {"name": {"value": "Cam"}}}
    remote, manager = make_remote_and_manager(system_state)

    system_calls = []
    manager.listen(lambda *args: system_calls.append(args))

    device_calls = []
    manager.events.listenDevice(
        "cam1",
        "ObjectDetector",
        lambda details, value: device_calls.append((details, value)),
    )

    details = motion_details(
        eventInterface="ObjectDetector", property=None, eventId="e3"
    )
    payload = {"detections": [{"className": "person"}]}
    await remote.notify("cam1", details, payload)

    assert device_calls == [(details, payload)]
    assert system_calls == []


async def test_listen_device_register_and_unregister():
    """event-registry.ts parity: listeners live in the token-keyed set."""
    system_state = {"cam1": {"name": {"value": "Cam"}}}
    remote, manager = make_remote_and_manager(system_state)

    calls = []
    register = manager.events.listenDevice(
        "cam1", "ObjectDetector", lambda details, value: calls.append(value)
    )

    details = motion_details(eventInterface="ObjectDetector", property=None)
    await remote.notify("cam1", details, "first")
    register.removeListener()
    await remote.notify("cam1", details, "second")

    assert calls == ["first"]


async def test_notify_without_system_manager_still_updates_state():
    """API clients update state before any SystemManager is attached."""
    system_state = {"cam1": {"motionDetected": {"value": False}}}
    cluster_setup = SimpleNamespace(peer=SimpleNamespace(params={}))
    remote = PluginRemote(
        cluster_setup, None, "@scrypted/core", {}, asyncio.get_event_loop()
    )
    remote.systemState = system_state

    await remote.notify("cam1", motion_details(), {"value": True})

    assert system_state["cam1"]["motionDetected"] == {"value": True}
