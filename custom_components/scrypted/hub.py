"""Connection lifecycle for the Scrypted engine.io RPC client."""

from __future__ import annotations

import asyncio
from collections import Counter
from functools import partial
import logging
from typing import Any

from scrypted_sdk import (
    EioRpcTransport,
    ScryptedConnectionError,
    ScryptedInterface,
    ScryptedStatic,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    SIGNAL_CONNECTION,
    SIGNAL_DETECTIONS,
    SIGNAL_DEVICE_UPDATE,
    SIGNAL_NEW_DEVICE,
)
from .sdk import async_connect_sdk

__all__ = ["ScryptedClient"]

_LOGGER = logging.getLogger(__name__)

RECONNECT_INITIAL_DELAY = 5
RECONNECT_MAX_DELAY = 300


class ScryptedClient:
    """Owns the SDK connection for a config entry and fans out events."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the client for a config entry."""
        self.hass = hass
        self.entry = entry
        self.sdk: ScryptedStatic | None = None
        self.transport: EioRpcTransport | None = None
        self.connected = False
        self._known_ids: set[str] = set()
        self._closing = False
        self._reconnect_task: asyncio.Task | None = None
        # Entities holding each device's shared ObjectDetector subscription,
        # and the live server-side registration for it.
        self._detection_refs: Counter[str] = Counter()
        self._detection_registers: dict[str, Any] = {}

    @property
    def host(self) -> str:
        """Return the configured scrypted host."""
        return self.entry.data[CONF_HOST]

    @property
    def device_ids(self) -> list[str]:
        """Return the ids of every device in the scrypted system state."""
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
        # Registrations die with the transport, so a reconnect renews every
        # subscription an entity still holds.
        for device_id in self._detection_refs:
            self._register_detections(device_id)

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
    def async_subscribe_detections(self, device_id: str) -> CALLBACK_TYPE:
        """Hold the device's shared ObjectDetector subscription; return a release.

        Stateless ObjectsDetected payloads never reach the system listener, and
        each listenDevice is its own server-side subscription carrying every
        payload, motion included, several times a second. Entities therefore
        share one per device and receive payloads on SIGNAL_DETECTIONS.
        """
        self._detection_refs[device_id] += 1
        if self._detection_refs[device_id] == 1:
            self._register_detections(device_id)

        @callback
        def _release() -> None:
            self._detection_refs[device_id] -= 1
            if self._detection_refs[device_id]:
                return
            del self._detection_refs[device_id]
            if register := self._detection_registers.pop(device_id, None):
                register.removeListener()

        return _release

    def _register_detections(self, device_id: str) -> None:
        if not self.sdk:
            return
        self._detection_registers[device_id] = self.sdk.systemManager.listenDevice(
            device_id,
            ScryptedInterface.ObjectDetector.value,
            partial(self._on_detections, device_id),
        )

    @callback
    def _on_detections(
        self, device_id: str, device: Any, event_details: dict, data: Any
    ) -> None:
        """Dispatch a detection payload; runs on the HA event loop (engine.io read task)."""
        async_dispatcher_send(
            self.hass,
            SIGNAL_DETECTIONS.format(self.entry.entry_id, device_id),
            data or {},
        )

    @callback
    def _handle_disconnect(self) -> None:
        if self._closing:
            return
        _LOGGER.warning("Scrypted %s disconnected; reconnecting", self.host)
        self.connected = False
        # The registrations died with the transport; removing one would RPC
        # over a closed peer.
        self._detection_registers.clear()
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
            except Exception:
                # Anything escaping here would end the task and leave the entry
                # offline until it is reloaded by hand.
                _LOGGER.exception("Unexpected error reconnecting to %s", self.host)
            await asyncio.sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX_DELAY)
