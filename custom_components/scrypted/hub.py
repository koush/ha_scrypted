"""Connection lifecycle for the Scrypted engine.io RPC client."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import SIGNAL_CONNECTION, SIGNAL_DEVICE_UPDATE, SIGNAL_NEW_DEVICE
from .sdk import (
    EioRpcTransport,
    ScryptedConnectionError,
    async_connect_sdk,
    get_base_url,
)
from scrypted_sdk import ScryptedStatic

__all__ = ["ScryptedClient", "ScryptedConnectionError", "get_base_url"]

_LOGGER = logging.getLogger(__name__)

RECONNECT_INITIAL_DELAY = 5
RECONNECT_MAX_DELAY = 300


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
