"""Low-level engine.io RPC transport for the Scrypted server.

Adapted from packages/python-client/test.py in the scrypted repo. This module
is intentionally thin and I/O-bound; it is excluded from unit test coverage
(see .coveragerc) and verified end-to-end with scripts/dev_connect.py.
"""
from __future__ import annotations

import asyncio
import logging

import aiohttp
import engineio

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import (
    async_create_clientsession,
    async_get_clientsession,
)

from .sdk_compat import ScryptedStatic, plugin_remote, rpc_reader

_LOGGER = logging.getLogger(__name__)

CONNECT_TIMEOUT = 30
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
    """RpcTransport over an engine.io connection."""

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        http_session: aiohttp.ClientSession | None = None,
    ) -> None:
        super().__init__()
        # Passing a session built by HA avoids engineio creating its own SSL
        # context inside the event loop (a blocking call HA warns about):
        # with ssl_verify left True, engineio defers entirely to the session's
        # connector, which HA builds with a cached no-verify context. Only
        # fall back to engineio's own ssl_verify=False (which calls
        # ssl.create_default_context at connect time) when no session is
        # provided. engineio never closes externally provided sessions, so we
        # own it.
        self._http_session = http_session
        self.eio = engineio.AsyncClient(
            http_session=http_session, ssl_verify=http_session is None
        )
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

    def writeSerialized(self, j, reject):
        # engineio json-encodes dict payloads on send and json-decodes text
        # frames on receive, so messages cross the wire as engine.io JSON
        # packets and arrive at readLoop() already deserialized to dicts.
        return self.writeBuffer(j, reject)

    async def close(self) -> None:
        """Tear the transport down."""
        if self._send_task:
            self._send_task.cancel()
        try:
            await self.eio.disconnect()
        except Exception:  # noqa: BLE001 - best effort teardown
            _LOGGER.debug("Error disconnecting engine.io client", exc_info=True)
        if self._http_session:
            await self._http_session.close()
            self._http_session = None


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
    transport = EioRpcTransport(
        loop, http_session=async_create_clientsession(hass, verify_ssl=False)
    )
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
        cluster_setup = plugin_remote.ClusterSetup(loop, peer)
        remote = plugin_remote.PluginRemote(
            cluster_setup, api, plugin_id_, host_info, loop
        )
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
